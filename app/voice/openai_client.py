import asyncio
import base64
import json
import os
import queue
import traceback

from app.voice.base_client import VoiceClient

RECONNECT_ATTEMPTS = 1


class OpenAIRealtimeClient(VoiceClient):
    # OpenAI Realtime uses 24 kHz PCM16 mono in both directions.
    INPUT_SAMPLE_RATE = 24000
    OUTPUT_SAMPLE_RATE = 24000

    def __init__(self, ui_queue: queue.Queue):
        super().__init__(ui_queue)
        self._ws = None
        self._turn_index = 0
        self._running = False
        self._assistant_buffer = ""
        self._user_buffer = ""

    async def connect(self, system_prompt: str, voice_config: dict) -> None:
        import websockets

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            self.emit({"type": "error", "message": "OPENAI_API_KEY not set. Check .env or Preferences."})
            self.emit({"type": "session_end"})
            return

        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        self._running = True
        for attempt in range(RECONNECT_ATTEMPTS + 1):
            try:
                async with websockets.connect(url, additional_headers=headers) as ws:
                    self._ws = ws
                    await self._send_event({
                        "type": "session.update",
                        "session": {
                            "modalities": ["text", "audio"],
                            "instructions": system_prompt,
                            "voice": voice_config.get("voice_name", "alloy"),
                            "input_audio_format": "pcm16",
                            "output_audio_format": "pcm16",
                            "input_audio_transcription": {"model": "whisper-1"},
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                            },
                        },
                    })
                    self.emit({"type": "status", "text": "Connected to OpenAI Realtime"})
                    # Optional AI-first kickoff (e.g. the interviewer greets the
                    # candidate): inject a hidden text turn and request a response.
                    kickoff = voice_config.get("kickoff_text")
                    if kickoff:
                        await self._send_event({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": kickoff}],
                            },
                        })
                        await self._send_event({"type": "response.create"})
                    await self._receive_loop()
                break
            except Exception as exc:
                if attempt < RECONNECT_ATTEMPTS and self._running:
                    self.emit({"type": "status", "text": f"Reconnecting… ({exc})"})
                    await asyncio.sleep(1.5)
                else:
                    self.emit({"type": "error", "message": f"OpenAI connection failed: {exc}"})
                    self.emit({"type": "session_end"})

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                event = json.loads(raw)
                etype = event.get("type", "")

                if etype == "response.audio_transcript.delta":
                    self._assistant_buffer += event.get("delta", "")

                elif etype == "response.audio_transcript.done":
                    text = event.get("transcript", self._assistant_buffer).strip()
                    if text:
                        self.emit({
                            "type": "transcript",
                            "role": "patient",
                            "turn_index": self._turn_index,
                            "text": text,
                        })
                        self._turn_index += 1
                    self._assistant_buffer = ""

                elif etype == "conversation.item.input_audio_transcription.completed":
                    text = event.get("transcript", "").strip()
                    if text:
                        self.emit({
                            "type": "transcript",
                            "role": "user",
                            "turn_index": self._turn_index,
                            "text": text,
                        })
                        self._turn_index += 1

                elif etype == "response.audio.delta":
                    audio_b64 = event.get("delta", "")
                    if audio_b64:
                        self.emit({"type": "audio_out", "data": base64.b64decode(audio_b64)})

                elif etype == "error":
                    err = event.get("error", {})
                    self.emit({"type": "error", "message": f"OpenAI error: {err.get('message', str(err))}"})

        except Exception as exc:
            if not self._running or exc.__class__.__name__ == "ConnectionClosedOK":
                # We closed the socket (End & Analyze) or it closed cleanly.
                self.emit({"type": "status", "text": "OpenAI session closed"})
                self.emit({"type": "session_end"})
                return
            self.emit({"type": "error", "message": f"OpenAI receive error: {exc}\n{traceback.format_exc()}"})
            self.emit({"type": "session_end"})

    async def _send_event(self, event: dict) -> None:
        if self._ws:
            await self._ws.send(json.dumps(event))

    async def send_audio_chunk(self, chunk: bytes) -> None:
        if self._ws and self._running:
            try:
                await self._send_event({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode(),
                })
            except Exception as exc:
                self.emit({"type": "error", "message": f"OpenAI send error: {exc}"})

    async def close(self) -> None:
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self.emit({"type": "status", "text": "OpenAI session closed"})
