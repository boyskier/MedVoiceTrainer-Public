import asyncio
import os
import queue
import traceback

from app.voice.base_client import VoiceClient

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
RECONNECT_ATTEMPTS = 1

# Live models come and go (gemini-2.0-flash-live-001 was retired); try these in
# order. The "-latest" alias is maintained by Google and should track the
# current native-audio live model. GEMINI_LIVE_MODEL in .env overrides.
CANDIDATE_LIVE_MODELS = [
    "gemini-2.5-flash-native-audio-latest",
    "gemini-3.1-flash-live-preview",
    "gemini-2.0-flash-live-001",
]


def _is_model_unavailable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "is not found" in msg or "not supported for bidigeneratecontent" in msg


def _is_normal_closure(exc: Exception) -> bool:
    """True for a clean websocket close (code 1000), which the genai SDK
    surfaces as an exception even when WE initiated the close."""
    if exc.__class__.__name__ == "ConnectionClosedOK":
        return True
    return str(exc).strip().startswith("1000")


class GeminiLiveClient(VoiceClient):
    # Gemini Live: microphone in at 16 kHz, model speech out at 24 kHz (PCM16 mono).
    INPUT_SAMPLE_RATE = 16000
    OUTPUT_SAMPLE_RATE = 24000

    def __init__(self, ui_queue: queue.Queue):
        super().__init__(ui_queue)
        self._session = None
        self._client = None
        self._turn_index = 0
        self._running = False

    async def connect(self, system_prompt: str, voice_config: dict) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            self.emit({"type": "error", "message": "google-genai package not installed. Run: pip install google-genai"})
            self.emit({"type": "session_end"})
            return

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            self.emit({"type": "error", "message": "GEMINI_API_KEY not set. Check .env or Preferences."})
            self.emit({"type": "session_end"})
            return

        self._client = genai.Client(api_key=api_key)

        # Gemini Live allows exactly ONE response modality. We use AUDIO for the
        # spoken patient and request transcription of BOTH directions so the full
        # conversation (student + patient) is captured as text for the DB and the
        # post-session analysis. Without these transcription configs the student's
        # turns would never be recorded.
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)],
                role="user",
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_config.get("voice_name", "Puck")
                    )
                )
            ),
        )

        self._running = True
        last_exc: Exception | None = None
        for model in self._candidate_models():
            attempt = 0
            while True:
                try:
                    async with self._client.aio.live.connect(model=model, config=config) as session:
                        self._session = session
                        self.emit({"type": "status", "text": f"Connected to Gemini Live ({model})"})
                        # Optional AI-first kickoff (e.g. the interviewer greets the
                        # candidate). Sent as a text client turn, so it never appears
                        # in the audio input transcription / saved transcript.
                        kickoff = voice_config.get("kickoff_text")
                        if kickoff:
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user", parts=[types.Part(text=kickoff)]
                                ),
                                turn_complete=True,
                            )
                        await self._receive_loop()
                    return
                except Exception as exc:
                    if _is_model_unavailable(exc):
                        last_exc = exc
                        break  # this model is gone/unsupported — try the next one
                    if attempt < RECONNECT_ATTEMPTS and self._running:
                        attempt += 1
                        self.emit({"type": "status", "text": f"Reconnecting… ({exc})"})
                        await asyncio.sleep(1.5)
                        continue
                    self.emit({"type": "error", "message": f"Gemini connection failed: {exc}"})
                    self.emit({"type": "session_end"})
                    return

        self.emit({
            "type": "error",
            "message": (
                "No usable Gemini Live model found for this API key. "
                f"Last error: {last_exc}\n"
                "You can pin one with GEMINI_LIVE_MODEL=<model-name> in .env."
            ),
        })
        self.emit({"type": "session_end"})

    def _candidate_models(self) -> list:
        """Live model names to try, best first.

        Order: .env override → known-good candidates → whatever the API says
        currently supports bidiGenerateContent (so a retired model name can
        never permanently brick voice sessions).
        """
        candidates = []
        override = os.environ.get("GEMINI_LIVE_MODEL", "").strip()
        if override:
            candidates.append(override)
        candidates.extend(CANDIDATE_LIVE_MODELS)
        try:
            for m in self._client.models.list():
                actions = getattr(m, "supported_actions", None) or []
                name = (m.name or "").removeprefix("models/")
                if ("bidiGenerateContent" in actions and name not in candidates
                        and "translate" not in name):
                    candidates.append(name)
        except Exception:
            pass  # listing is best-effort; static candidates remain
        return candidates

    async def _receive_loop(self) -> None:
        user_buffer = ""        # student speech (input transcription)
        assistant_buffer = ""   # patient speech (output transcription)
        try:
            # session.receive() iterates ONE model turn and stops at
            # turn_complete, so it must be re-entered for every turn —
            # otherwise the session dies after the first exchange.
            while self._running:
                async for response in self._session.receive():
                    if not self._running:
                        break


                    sc = response.server_content
                    if sc is not None:
                        if sc.input_transcription and sc.input_transcription.text:
                            user_buffer += sc.input_transcription.text
                        if sc.output_transcription and sc.output_transcription.text:
                            assistant_buffer += sc.output_transcription.text

                        if sc.turn_complete:
                            # Emit the student's turn first, then the patient's reply,
                            # so transcript ordering matches the real exchange.
                            if user_buffer.strip():
                                self.emit({
                                    "type": "transcript",
                                    "role": "user",
                                    "turn_index": self._turn_index,
                                    "text": user_buffer.strip(),
                                })
                                self._turn_index += 1
                                user_buffer = ""
                            if assistant_buffer.strip():
                                self.emit({
                                    "type": "transcript",
                                    "role": "patient",
                                    "turn_index": self._turn_index,
                                    "text": assistant_buffer.strip(),
                                })
                                self._turn_index += 1
                                assistant_buffer = ""

                    if response.data:
                        self.emit({"type": "audio_out", "data": response.data})

        except Exception as exc:
            if not self._running or _is_normal_closure(exc):
                # We closed the session (End & Analyze) or the server closed it
                # cleanly — not an error.
                self.emit({"type": "status", "text": "Gemini session closed"})
                self.emit({"type": "session_end"})
                return
            self.emit({"type": "error", "message": f"Gemini receive error: {exc}\n{traceback.format_exc()}"})
            self.emit({"type": "session_end"})

        finally:
            if user_buffer.strip():
                self.emit({
                    "type": "transcript",
                    "role": "user",
                    "turn_index": self._turn_index,
                    "text": user_buffer.strip() + " [interrupted]",
                })
                self._turn_index += 1

    async def send_audio_chunk(self, chunk: bytes) -> None:
        if self._session and self._running:
            try:
                from google.genai import types
                await self._session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            except Exception as exc:
                # Don't spam one error per mic chunk when the socket is simply
                # closed/closing — only surface real failures mid-session.
                if self._running and not _is_normal_closure(exc):
                    self.emit({"type": "error", "message": f"Gemini send error: {exc}"})

    async def close(self) -> None:
        self._running = False
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
        self.emit({"type": "status", "text": "Gemini session closed"})
