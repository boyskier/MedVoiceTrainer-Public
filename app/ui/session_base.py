"""
Shared session control UI used by EncounterTab, InterviewTab, and CustomTab.
Provides: transcript display, start/stop controls, timer, mic indicator,
queue polling, and the full session lifecycle.
"""
import array
import asyncio
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

import config
from app.db import queries


PATIENT_BG = "#dbeafe"   # blue-50
USER_BG    = "#dcfce7"   # green-50
SYSTEM_BG  = "#fef9c3"   # yellow-50
ERROR_BG   = "#fee2e2"   # red-50


class SessionBase:
    """Base class mixed into each tab frame. Not a tk.Frame itself."""

    def __init__(self, parent_frame: tk.Frame, dev_mode: bool = False):
        self.parent_frame = parent_frame
        self.dev_mode = dev_mode

        self._ui_queue: queue.Queue = queue.Queue()
        self._voice_client = None
        self._voice_thread: Optional[threading.Thread] = None
        self._voice_loop: Optional[asyncio.AbstractEventLoop] = None

        self._session_id: Optional[int] = None
        self._transcript: list[dict] = []
        self._running = False
        self._audio_capture = None
        self._audio_player = None
        self._start_time: Optional[float] = None
        self._timer_after_id = None
        self._time_limit_secs: Optional[int] = None
        self._time_up_notified = False
        self._mic_state = "idle"
        self._mic_level = 0.0       # RMS of the latest mic chunk (PortAudio thread writes)
        self._mic_peak = 0.0        # session peak, for the "mic seems dead" warning
        self._low_mic_warned = False

        # These must be set by subclass before _build_session_ui is called
        self.mode: str = "encounter"
        self.current_case: Optional[dict] = None
        self.current_eval: Optional[dict] = None

    # ── Build shared UI (call from subclass) ─────────────────────────────────

    def _build_session_ui(self, container: tk.Frame) -> None:
        """Build transcript + controls area into container."""
        # Pre-session checklist (collapsible)
        self._checklist_frame = tk.Frame(container, bg="#f0f4ff", relief=tk.RIDGE, bd=1)
        self._checklist_frame.pack(fill=tk.X, padx=6, pady=(0, 4))
        self._checklist_visible = tk.BooleanVar(value=False)
        cl_header = tk.Frame(self._checklist_frame, bg="#f0f4ff")
        cl_header.pack(fill=tk.X)
        self._cl_toggle_btn = tk.Button(
            cl_header, text="▶ Pre-session Checklist", font=("Segoe UI", 9, "bold"),
            bg="#f0f4ff", relief=tk.FLAT, anchor="w",
            command=self._toggle_checklist,
        )
        self._cl_toggle_btn.pack(fill=tk.X, padx=6, pady=2)
        self._cl_items_frame = tk.Frame(self._checklist_frame, bg="#f0f4ff")

        # Phrase Helper (Foundations / coaching cases only; toggled via refresh_phrase_helper)
        self._build_phrase_helper(container)

        # Transcript
        transcript_frame = tk.Frame(container)
        self._transcript_container = transcript_frame
        transcript_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        self._transcript_text = tk.Text(
            transcript_frame, state=tk.DISABLED, wrap=tk.WORD,
            font=("Segoe UI", 10), bg="#ffffff", relief=tk.FLAT,
            selectbackground="#93c5fd",
        )
        scrollbar = ttk.Scrollbar(transcript_frame, command=self._transcript_text.yview)
        self._transcript_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._transcript_text.pack(fill=tk.BOTH, expand=True)

        self._transcript_text.tag_configure("patient", background=PATIENT_BG, lmargin1=8, lmargin2=8, spacing3=4)
        self._transcript_text.tag_configure("user", background=USER_BG, lmargin1=8, lmargin2=8, spacing3=4)
        self._transcript_text.tag_configure("system", background=SYSTEM_BG, lmargin1=4, lmargin2=4, spacing3=2)
        self._transcript_text.tag_configure("error", background=ERROR_BG, lmargin1=4, lmargin2=4, spacing3=2)
        self._transcript_text.tag_configure("turn_label", font=("Segoe UI", 8, "bold"), foreground="#6b7280")

        # Controls bar
        ctrl_frame = tk.Frame(container, bg="#f3f4f6", relief=tk.RIDGE, bd=1)
        ctrl_frame.pack(fill=tk.X, padx=6, pady=(2, 4))

        self._start_btn = ttk.Button(ctrl_frame, text="● Start", command=self._on_start)
        self._start_btn.pack(side=tk.LEFT, padx=6, pady=6)

        self._stop_btn = ttk.Button(ctrl_frame, text="■ End & Analyze", command=self._on_stop, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=4, pady=6)

        self._add_extra_controls(ctrl_frame)

        self._timer_label = ttk.Label(ctrl_frame, text="⏱ 00:00", style="Status.TLabel")
        self._timer_label.pack(side=tk.LEFT, padx=10)

        self._mic_label = ttk.Label(ctrl_frame, text="🎤 Idle", style="Status.TLabel")
        self._mic_label.pack(side=tk.LEFT, padx=4)

        if self.dev_mode:
            dev_badge = ttk.Label(ctrl_frame, text="[DEV MODE]", foreground="red", style="Status.TLabel")
            dev_badge.pack(side=tk.RIGHT, padx=8)

    def _toggle_checklist(self) -> None:
        if self._checklist_visible.get():
            self._cl_items_frame.pack_forget()
            self._checklist_visible.set(False)
            self._cl_toggle_btn.config(text="▶ Pre-session Checklist")
        else:
            self._populate_checklist()
            self._cl_items_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
            self._checklist_visible.set(True)
            self._cl_toggle_btn.config(text="▼ Pre-session Checklist")

    def _populate_checklist(self) -> None:
        for w in self._cl_items_frame.winfo_children():
            w.destroy()
        if not self.current_eval:
            tk.Label(self._cl_items_frame, text="No eval template loaded.", bg="#f0f4ff",
                     font=("Segoe UI", 9)).pack(anchor="w")
            return
        items = self.current_eval.get("checklist", [])
        for item in items:
            label = item.get("item", "")
            req = " *" if item.get("required") else ""
            tk.Label(self._cl_items_frame, text=f"  ✦ {label}{req}",
                     bg="#f0f4ff", font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)
        tk.Label(self._cl_items_frame, text="  * = required", bg="#f0f4ff",
                 font=("Segoe UI", 8), foreground="#6b7280").pack(anchor="w")

    # ── Phrase Helper (beginner cue card) ─────────────────────────────────────

    _PH_TITLE = "💬 Phrase Helper — sample things you can say"

    def _build_phrase_helper(self, container: tk.Frame) -> None:
        self._phrase_bank_cache = None
        self._phrase_frame = tk.Frame(container, bg="#ecfdf5", relief=tk.RIDGE, bd=1)
        self._phrase_visible = tk.BooleanVar(value=False)
        header = tk.Frame(self._phrase_frame, bg="#ecfdf5")
        header.pack(fill=tk.X)
        self._ph_toggle_btn = tk.Button(
            header, text="▶ " + self._PH_TITLE, font=("Segoe UI", 9, "bold"),
            bg="#ecfdf5", relief=tk.FLAT, anchor="w", command=self._toggle_phrase_helper,
        )
        self._ph_toggle_btn.pack(fill=tk.X, padx=6, pady=2)

        self._ph_body = tk.Frame(self._phrase_frame, bg="#ecfdf5")
        self._ph_text = tk.Text(
            self._ph_body, wrap=tk.WORD, height=9, font=("Segoe UI", 10),
            bg="#ffffff", relief=tk.FLAT, padx=8, pady=6, cursor="arrow",
        )
        sb = ttk.Scrollbar(self._ph_body, command=self._ph_text.yview)
        self._ph_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._ph_text.pack(fill=tk.BOTH, expand=True)
        self._ph_text.tag_configure("case", font=("Segoe UI", 9, "bold"), foreground="#b45309", spacing1=4)
        self._ph_text.tag_configure("cat", font=("Segoe UI", 9, "bold"), foreground="#047857", spacing1=8)
        self._ph_text.tag_configure("phrase", font=("Segoe UI", 10), foreground="#111827", lmargin1=16, lmargin2=24)
        self._ph_text.tag_configure("hint", font=("Segoe UI", 8, "italic"), foreground="#6b7280", spacing1=6)

    def _load_phrase_bank(self) -> dict:
        if self._phrase_bank_cache is not None:
            return self._phrase_bank_cache
        try:
            with open(config.FOUNDATIONS_PHRASES_PATH, encoding="utf-8") as f:
                self._phrase_bank_cache = json.load(f)
        except Exception:
            self._phrase_bank_cache = {"categories": []}
        return self._phrase_bank_cache

    def _toggle_phrase_helper(self) -> None:
        if self._phrase_visible.get():
            self._ph_body.pack_forget()
            self._phrase_visible.set(False)
            self._ph_toggle_btn.config(text="▶ " + self._PH_TITLE)
        else:
            self._ph_body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
            self._phrase_visible.set(True)
            self._ph_toggle_btn.config(text="▼ " + self._PH_TITLE)

    def _populate_phrase_helper(self, case: dict) -> None:
        txt = self._ph_text
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)
        suggested = case.get("suggested_questions") or []
        if suggested:
            txt.insert(tk.END, "★ For this patient — try asking:\n", "case")
            for s in suggested:
                txt.insert(tk.END, f"• {s}\n", "phrase")
        # Skill drills can supply their own cue-card categories; otherwise use
        # the shared encounter phrase bank.
        categories = case.get("phrase_categories")
        if categories is None:
            categories = self._load_phrase_bank().get("categories", [])
        for cat in categories:
            txt.insert(tk.END, f"{cat.get('name', '')}\n", "cat")
            for p in cat.get("phrases", []):
                txt.insert(tk.END, f"• {p}\n", "phrase")
        txt.insert(tk.END, "\nRead a line aloud to start, then make it your own.\n", "hint")
        txt.config(state=tk.DISABLED)

    def refresh_phrase_helper(self) -> None:
        """Show the cue card for coaching/Foundations cases and for any case
        that ships its own phrase material (e.g. SBAR scaffolding); hide it
        otherwise."""
        if not hasattr(self, "_phrase_frame"):
            return
        case = self.current_case or {}
        if (case.get("coaching_mode") or case.get("phrase_categories")
                or case.get("suggested_questions")):
            self._populate_phrase_helper(case)
            if not self._phrase_frame.winfo_ismapped():
                self._phrase_frame.pack(fill=tk.X, padx=6, pady=(0, 4),
                                        before=self._transcript_container)
            if not self._phrase_visible.get():
                self._toggle_phrase_helper()  # start expanded for beginners
        else:
            self._phrase_frame.pack_forget()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def _on_start(self) -> None:
        if not self.current_case:
            messagebox.showwarning("No case selected", "Please select a case or scenario before starting.")
            return

        # Collapse checklist
        if self._checklist_visible.get():
            self._toggle_checklist()

        self._transcript.clear()
        self._clear_transcript_display()
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._running = True
        self._start_time = time.time()
        self._time_limit_secs = self._resolve_time_limit()
        self._time_up_notified = False
        self._mic_level = 0.0
        self._mic_peak = 0.0
        self._low_mic_warned = False
        self._tick_timer()

        # Build the system prompt BEFORE creating the session row: prompt
        # building may enrich self.current_case for this session (e.g. the
        # randomly assigned complexity modifier), and that enriched case must
        # be the one persisted to raw_case_json so the post-session analysis
        # sees exactly what the live patient was instructed to do.
        system_prompt = self._build_system_prompt()

        backend = queries.get_setting("voice_backend", "gemini")
        self._session_id = queries.create_session(
            mode=self.mode,
            case_name=self.current_case.get("patient_name") or self.current_case.get("id", "custom"),
            case_id=self.current_case.get("id"),
            eval_template=self.current_eval.get("name") if self.current_eval else None,
            voice_backend="mock" if self.dev_mode else backend,
            raw_case_json=self.current_case,
            raw_eval_json=self.current_eval,
        )

        # Leave voice_name unset so each backend applies its own valid default
        # (Gemini → "Puck", OpenAI → "alloy"). Passing a Gemini-only voice name
        # to the OpenAI Realtime API would be rejected as invalid.
        voice_config: dict = {}
        if self.mode == "interview":
            # The interviewer speaks first, as in a real interview. Each backend
            # turns this into its own "AI opens the conversation" mechanism.
            voice_config["kickoff_text"] = (
                "(The candidate has just entered the room and sat down. "
                "Greet them briefly and ask your opening question.)"
            )

        from app.voice.factory import create_voice_client
        self._voice_client = create_voice_client(self._ui_queue, dev_mode=self.dev_mode, mode=self.mode)

        self._voice_loop = asyncio.new_event_loop()
        self._voice_thread = threading.Thread(
            target=self._run_voice_loop,
            args=(system_prompt, voice_config),
            daemon=True,
        )
        self._voice_thread.start()

        self._start_audio_io()
        self._set_mic_status("listening", "🎤 Listening…")
        self.parent_frame.after(config.QUEUE_POLL_MS, self._poll_queue)

    # ── Audio I/O (microphone in, speaker out) ───────────────────────────────

    def _start_audio_io(self) -> None:
        """Open the mic capture + speaker playback streams for a live session.

        Skipped entirely in dev/mock mode (no real audio). Any failure here is
        non-fatal: the session still runs, the user just sees an inline notice.
        """
        if self.dev_mode:
            return
        from app.voice.audio_io import (
            AudioCapture, AudioPlayer, resolve_input_device,
            resolve_output_device, sounddevice_available,
        )
        if not sounddevice_available():
            self._append_error_message(
                "sounddevice not installed — no microphone or audio playback. "
                "Run: pip install sounddevice"
            )
            return

        in_rate = getattr(self._voice_client, "INPUT_SAMPLE_RATE", 16000)
        out_rate = getattr(self._voice_client, "OUTPUT_SAMPLE_RATE", 24000)

        try:
            out_name = queries.get_setting("output_device", "")
            out_dev = resolve_output_device(out_name)
            if out_name and out_dev is None:
                self._append_system_message(
                    f'Saved speaker "{out_name}" not found — using the system default.'
                )
            self._audio_player = AudioPlayer(out_rate, device=out_dev)
            self._audio_player.start()
        except Exception as exc:
            self._audio_player = None
            self._append_error_message(f"Audio output unavailable: {exc}")

        try:
            device_name = queries.get_setting("input_device", "")
            device = resolve_input_device(device_name)
            if device_name and device is None:
                self._append_system_message(
                    f'Saved microphone "{device_name}" not found — using the system default.'
                )
            self._audio_capture = AudioCapture(self._on_mic_chunk, in_rate, device=device)
            self._audio_capture.start()
        except Exception as exc:
            self._audio_capture = None
            self._append_error_message(
                f"Microphone unavailable: {exc}\n"
                "Check your input device and OS microphone permissions."
            )

    def _on_mic_chunk(self, data: bytes) -> None:
        """Forward a captured PCM chunk to the voice client (PortAudio thread)."""
        loop = self._voice_loop
        client = self._voice_client
        if not (self._running and loop and client and not loop.is_closed()):
            return
        # Track the input level so the UI can show a live mic meter (and warn
        # when the mic appears dead). int16 mono PCM.
        samples = array.array("h")
        samples.frombytes(data[: len(data) - (len(data) % 2)])
        if samples:
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            self._mic_level = rms
            if rms > self._mic_peak:
                self._mic_peak = rms
        try:
            asyncio.run_coroutine_threadsafe(client.send_audio_chunk(data), loop)
        except RuntimeError:
            # Loop finished/closed between the guard and the scheduling call.
            pass

    def _stop_audio_io(self) -> None:
        if self._audio_capture is not None:
            self._audio_capture.stop()
            self._audio_capture = None
        if self._audio_player is not None:
            self._audio_player.stop()
            self._audio_player = None

    def _run_voice_loop(self, system_prompt: str, voice_config: dict) -> None:
        asyncio.set_event_loop(self._voice_loop)
        try:
            self._voice_loop.run_until_complete(
                self._voice_client.connect(system_prompt, voice_config)
            )
            # Some clients (e.g. the mock) schedule background tasks via
            # create_task and return immediately from connect(). Drain those
            # tasks so the session actually plays out instead of being dropped
            # the moment connect() resolves.
            pending = asyncio.all_tasks(self._voice_loop)
            if pending:
                self._voice_loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            self._voice_loop.close()

    def _on_stop(self) -> None:
        self._running = False
        self._stop_audio_io()
        if self._timer_after_id:
            self.parent_frame.after_cancel(self._timer_after_id)
        if self._voice_client and self._voice_loop and not self._voice_loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._voice_client.close(), self._voice_loop)
            except RuntimeError:
                # Loop already finished/closed between the guard and the call.
                pass

        self._stop_btn.config(state=tk.DISABLED)
        self._set_mic_status("idle", "🎤 Idle")

        duration = int(time.time() - self._start_time) if self._start_time else 0
        self._start_time = None

        # The voice client may still be flushing its final transcript events
        # (e.g. the transcription of the last exchange). Give them a short
        # grace period and drain the queue once more before analysing, so the
        # closing turns are not silently dropped from the analysis. Start stays
        # disabled until then so a new session cannot race the old one's events.
        self.parent_frame.after(600, lambda: self._finish_session(duration))

    def _finish_session(self, duration: int) -> None:
        self._drain_queue()
        self._start_btn.config(state=tk.NORMAL)
        if self._transcript:
            self._run_analysis(duration)
        else:
            self._append_system_message("Session ended with no transcript.")
            queries.finalize_empty_session(self._session_id, duration)

    # ── Queue polling (main thread only) ─────────────────────────────────────

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self._ui_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

    _LEVEL_BARS = "▁▂▃▄▅▆▇█"
    # RMS thresholds per bar step — roughly logarithmic so quiet mics still
    # visibly register speech.
    _LEVEL_THRESHOLDS = (50, 100, 200, 400, 800, 1600, 3200)

    @classmethod
    def _level_bar(cls, rms: float) -> str:
        idx = sum(1 for t in cls._LEVEL_THRESHOLDS if rms >= t)
        return cls._LEVEL_BARS[idx]

    def _poll_queue(self) -> None:
        self._drain_queue()
        if self._running:
            # While the AI's speech is still playing show "Speaking"; once the
            # playback buffer drains, flip back to "Listening" so the student
            # knows it is their turn.
            if (self._mic_state == "speaking"
                    and (self._audio_player is None
                         or self._audio_player.buffered_bytes == 0)):
                self._set_mic_status("listening", "🎤 Listening…")
            # Live mic level meter so the student can SEE whether their voice
            # is actually being picked up.
            if self._mic_state == "listening" and self._audio_capture is not None:
                self._mic_label.config(text=f"🎤 Listening… {self._level_bar(self._mic_level)}")
            self._check_mic_health()
            self.parent_frame.after(config.QUEUE_POLL_MS, self._poll_queue)

    def _check_mic_health(self) -> None:
        """Warn once if, well into the session, the mic has only ever produced
        near-silence — the most common cause of 'the AI never answers me'."""
        if self._audio_capture is not None and hasattr(self._audio_capture, "ensure_alive"):
            self._audio_capture.ensure_alive()

        if (self._low_mic_warned or self._audio_capture is None
                or not self._start_time):
            return
        if time.time() - self._start_time > 12 and self._mic_peak < 200:
            self._low_mic_warned = True
            self._append_error_message(
                "Your voice doesn't seem to be reaching the microphone — the input "
                "level has stayed near zero since the session started.\n"
                "Check: Windows Settings → System → Sound → Input: pick the right "
                "device and raise its volume, then restart the session."
            )

    def _handle_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "transcript":
            role = event.get("role", "user")
            text = event.get("text", "")
            turn_idx = event.get("turn_index", len(self._transcript))
            turn = {"turn_index": turn_idx, "role": role, "text": text}
            self._transcript.append(turn)
            if self._session_id:
                queries.append_turn(self._session_id, turn)
            self._append_transcript_turn(role, text, turn_idx)
            if role == "user":
                self._on_user_turn(text)

        elif etype == "status":
            self._set_mic_status("listening", event.get("text", ""))

        elif etype == "audio_out":
            data = event.get("data")
            if data and self._audio_player is not None:
                self._audio_player.play(data)
            self._set_mic_status("speaking", "🔊 AI Speaking…")

        elif etype == "error":
            self._append_error_message(event.get("message", "Unknown error"))

        elif etype == "session_end":
            if self._running:
                self._on_stop()

    # ── Transcript display ────────────────────────────────────────────────────

    def _append_transcript_turn(self, role: str, text: str, turn_index: int) -> None:
        tw = self._transcript_text
        tw.config(state=tk.NORMAL)
        tag = "patient" if role in ("patient", "interviewer") else "user"
        label = role.upper()
        tw.insert(tk.END, f"[{turn_index}] {label}\n", "turn_label")
        tw.insert(tk.END, f"{text}\n\n", tag)
        tw.config(state=tk.DISABLED)
        tw.see(tk.END)

    def _append_system_message(self, text: str) -> None:
        tw = self._transcript_text
        tw.config(state=tk.NORMAL)
        tw.insert(tk.END, f"ℹ {text}\n\n", "system")
        tw.config(state=tk.DISABLED)
        tw.see(tk.END)

    def _append_error_message(self, text: str) -> None:
        tw = self._transcript_text
        tw.config(state=tk.NORMAL)
        tw.insert(tk.END, f"⚠ {text}\n\n", "error")
        tw.config(state=tk.DISABLED)
        tw.see(tk.END)

    def _clear_transcript_display(self) -> None:
        self._transcript_text.config(state=tk.NORMAL)
        self._transcript_text.delete("1.0", tk.END)
        self._transcript_text.config(state=tk.DISABLED)

    # ── Timer ─────────────────────────────────────────────────────────────────

    # Default station lengths (minutes) when the case does not set its own
    # "station_minutes" — modelled on a typical OSCE station and a standard
    # residency interview slot. Coaching/beginner cases run untimed.
    DEFAULT_STATION_MINUTES = {"encounter": 8, "interview": 10}

    def _resolve_time_limit(self) -> Optional[int]:
        case = self.current_case or {}
        explicit = case.get("station_minutes")
        if explicit:
            try:
                return int(float(explicit) * 60)
            except (TypeError, ValueError):
                pass
        if case.get("coaching_mode"):
            return None  # no time pressure for beginners
        minutes = self.DEFAULT_STATION_MINUTES.get(self.mode)
        return minutes * 60 if minutes else None

    def _tick_timer(self) -> None:
        if not self._running or not self._start_time:
            return
        elapsed = int(time.time() - self._start_time)
        minutes, seconds = divmod(elapsed, 60)
        text = f"⏱ {minutes:02d}:{seconds:02d}"
        color = "#374151"
        limit = self._time_limit_secs
        if limit:
            lm, ls = divmod(limit, 60)
            text += f" / {lm:02d}:{ls:02d}"
            remaining = limit - elapsed
            if remaining <= 0:
                color = "#dc2626"
                if not self._time_up_notified:
                    self._time_up_notified = True
                    self._append_system_message(
                        "⏰ Station time is up — wrap up now: summarize, "
                        "check understanding, and close."
                    )
            elif remaining <= 120:
                color = "#d97706"
        self._timer_label.config(text=text, foreground=color)
        self._timer_after_id = self.parent_frame.after(1000, self._tick_timer)

    # ── Mic indicator ────────────────────────────────────────────────────────

    def _set_mic_status(self, state: str, text: str) -> None:
        colors = {"listening": "#16a34a", "speaking": "#d97706", "idle": "#9ca3af"}
        self._mic_state = state
        self._mic_label.config(text=text, foreground=colors.get(state, "#9ca3af"))

    # ── Analysis flow ────────────────────────────────────────────────────────

    def _run_analysis(self, duration: int) -> None:
        self._append_system_message("Analysing session… please wait.")
        self._show_self_assessment_dialog(duration)

    def _show_self_assessment_dialog(self, duration: int) -> None:
        if not self.current_eval:
            self._check_soap_note_dialog(duration, self_scores=None)
            return

        metrics = self.current_eval.get("metrics", {})
        if not metrics:
            self._check_soap_note_dialog(duration, self_scores=None)
            return

        dialog = tk.Toplevel(self.parent_frame)
        dialog.title("Self-Assessment")
        # No fixed geometry: size to content so the sliders and the submit
        # button are never clipped on high-DPI displays.
        dialog.resizable(False, False)
        dialog.grab_set()

        # Anchored to the bottom edge first so it can never be the clipped part.
        submit_btn = ttk.Button(dialog, text="Submit Self-Assessment")
        submit_btn.pack(side=tk.BOTTOM, pady=16)

        tk.Label(dialog, text="How did you feel you performed?",
                 font=("Segoe UI", 11, "bold")).pack(pady=(16, 4))
        tk.Label(dialog, text="Rate yourself on each dimension (0 = poor, 10 = excellent)",
                 font=("Segoe UI", 9), foreground="#6b7280").pack(pady=(0, 12))

        sliders: dict[str, tk.DoubleVar] = {}
        for key, meta in metrics.items():
            row = tk.Frame(dialog)
            row.pack(fill=tk.X, padx=20, pady=4)
            tk.Label(row, text=meta.get("label", key), width=26, anchor="w",
                     font=("Segoe UI", 10)).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=5.0)
            sliders[key] = var
            scale = ttk.Scale(row, from_=0, to=10, orient=tk.HORIZONTAL, variable=var, length=160)
            scale.pack(side=tk.LEFT, padx=8)
            val_label = tk.Label(row, text="5.0", width=4, font=("Segoe UI", 10))
            val_label.pack(side=tk.LEFT)
            scale.config(command=lambda v, lbl=val_label: lbl.config(text=f"{float(v):.1f}"))

        def submit():
            self_scores = {k: round(v.get(), 1) for k, v in sliders.items()}
            if self._session_id:
                queries.save_self_scores(self._session_id, self_scores)
            dialog.destroy()
            self._check_soap_note_dialog(duration, self_scores=self_scores)

        submit_btn.config(command=submit)
        dialog.wait_window()

    def _check_soap_note_dialog(self, duration: int, self_scores: Optional[dict]) -> None:
        if queries.get_setting("student_soap_note_typing") == "true":
            dialog = tk.Toplevel(self.parent_frame)
            dialog.title("Write Your SOAP Note")
            dialog.grab_set()

            soap_btn = ttk.Button(dialog, text="Submit SOAP Note")
            soap_btn.pack(side=tk.BOTTOM, pady=16)

            tk.Label(dialog, text="Please write your SOAP note based on the encounter.", font=("Segoe UI", 11, "bold")).pack(pady=10)

            soap_vars = {}
            for key, label in [("subjective", "Subjective (S)"), ("objective", "Objective (O)"), ("assessment", "Assessment (A)"), ("plan", "Plan (P)")]:
                tk.Label(dialog, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10)
                text = tk.Text(dialog, height=4, font=("Segoe UI", 10))
                text.pack(fill=tk.X, padx=10, pady=2)
                soap_vars[key] = text

            def submit_soap():
                soap_text = {k: v.get("1.0", tk.END).strip() for k, v in soap_vars.items()}
                combined = json.dumps(soap_text)
                if self._session_id:
                    queries.save_student_soap(self._session_id, combined)
                dialog.destroy()
                self._do_analysis(duration, self_scores, student_soap=soap_text)

            soap_btn.config(command=submit_soap)
            dialog.wait_window()
        else:
            self._do_analysis(duration, self_scores)

    def _do_analysis(
        self,
        duration: int,
        self_scores: Optional[dict],
        student_soap: Optional[dict] = None,
        session_id: Optional[int] = None,
        transcript: Optional[list] = None,
        case: Optional[dict] = None,
        eval_data: Optional[dict] = None,
    ) -> None:
        # Snapshot the session's state up front. The analysis runs in a worker
        # thread; meanwhile the user can start a new session or change the case,
        # which would otherwise mutate self._session_id / self._transcript /
        # self.current_case under the worker's feet (results saved to the wrong
        # row, or analysed against the wrong case). On retry these are re-passed.
        if session_id is None:
            session_id = self._session_id
        if transcript is None:
            transcript = list(self._transcript)
        if case is None:
            case = self.current_case or {}
        if eval_data is None:
            eval_data = self.current_eval or {}

        def worker():
            try:
                if self.dev_mode:
                    from app.analysis.feedback_engine import MockAnalysisEngine
                    result = MockAnalysisEngine.run(
                        transcript, case, eval_data, self_scores, session_id, student_soap,
                        duration_seconds=duration,
                    )
                else:
                    from app.analysis.feedback_engine import run_analysis
                    result = run_analysis(
                        transcript, case, eval_data, self_scores, session_id, student_soap,
                        duration_seconds=duration,
                    )
                if session_id:
                    queries.finalize_session(session_id, duration, result)
                self.parent_frame.after(0, lambda: self._open_feedback(result, self_scores, session_id))
            except Exception as exc:
                import traceback
                tb = traceback.format_exc()
                from app.db.database import log_event
                log_event("ERROR", f"Analysis failed: {exc}", session_id, tb)
                self.parent_frame.after(
                    0,
                    lambda: self._show_retry_analysis(
                        duration, self_scores, student_soap, str(exc),
                        session_id, transcript, case, eval_data,
                    )
                )

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _open_feedback(self, result: dict, self_scores: Optional[dict], session_id: Optional[int]) -> None:
        session = queries.get_session(session_id) if session_id else {}
        from app.ui.feedback_window import FeedbackWindow
        FeedbackWindow(self.parent_frame, session=session or {}, analysis=result)
        self._append_system_message("Analysis complete. Feedback window opened.")

    def _show_retry_analysis(
        self,
        duration: int,
        self_scores: Optional[dict],
        student_soap: Optional[dict],
        error: str,
        session_id: Optional[int],
        transcript: list,
        case: dict,
        eval_data: dict,
    ) -> None:
        self._append_error_message(f"Analysis failed: {error}")
        frame = tk.Frame(self.parent_frame, bg="#fee2e2")
        frame.pack(fill=tk.X, padx=6)
        tk.Button(
            frame, text="Retry Analysis", bg="#dc2626", fg="white",
            font=("Segoe UI", 10, "bold"),
            command=lambda: (
                frame.destroy(),
                self._do_analysis(duration, self_scores, student_soap,
                                  session_id, transcript, case, eval_data),
            ),
        ).pack(pady=4)

    # ── To be implemented by subclass ─────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        raise NotImplementedError

    def _add_extra_controls(self, ctrl_frame: tk.Frame) -> None:
        """Subclasses may add mode-specific buttons to the controls bar."""

    def _on_user_turn(self, text: str) -> None:
        """Called on the main thread for every transcribed student turn."""
