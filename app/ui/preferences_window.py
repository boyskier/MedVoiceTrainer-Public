import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from app.db.queries import get_setting, set_setting


class PreferencesWindow:
    def __init__(self, parent: tk.Widget):
        self.win = tk.Toplevel(parent)
        self.win.title("Preferences")
        # No fixed geometry: let tk size the window to its content so nothing
        # (especially the Save button) gets clipped on high-DPI displays.
        self.win.resizable(False, True)
        self.win.grab_set()
        self._test_capture = None
        self._test_level = 0.0
        self._build_ui()
        self._load_settings()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # Re-scan audio devices so earbuds (re)connected after app launch
        # appear in the pickers below.
        try:
            from app.voice.audio_io import refresh_devices
            refresh_devices()
        except Exception:
            pass

        # Pack the Save button FIRST anchored to the bottom edge: pack gives
        # space to earlier widgets first, so even if the screen is too short
        # for all the settings, Save is never the part that gets clipped.
        ttk.Button(self.win, text="Save", command=self._save).pack(side=tk.BOTTOM, pady=12)

        outer = tk.Frame(self.win, padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)

        # Voice backend
        tk.Label(outer, text="Voice Backend", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._backend_var = tk.StringVar(value="gemini")
        ttk.Radiobutton(outer, text="Gemini Live", variable=self._backend_var, value="gemini").grid(
            row=1, column=0, sticky="w", padx=8)
        ttk.Radiobutton(outer, text="OpenAI Realtime", variable=self._backend_var, value="openai").grid(
            row=1, column=1, sticky="w")

        # Feedback / analysis backend — the post-session feedback can run on any
        # provider, so the user only needs the one API key they already have.
        tk.Label(outer, text="Feedback AI (post-session analysis)", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self._feedback_var = tk.StringVar(value="claude")
        fb_row = tk.Frame(outer)
        fb_row.grid(row=3, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Radiobutton(fb_row, text="Claude", variable=self._feedback_var, value="claude").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(fb_row, text="Gemini", variable=self._feedback_var, value="gemini").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(fb_row, text="OpenAI", variable=self._feedback_var, value="openai").pack(side=tk.LEFT)

        # Microphone (input device) + live level test
        tk.Label(outer, text="Microphone", font=("Segoe UI", 10, "bold")).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(12, 4))
        mic_row = tk.Frame(outer)
        mic_row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8)
        self._mic_var = tk.StringVar(value="(system default)")
        devices = ["(system default)"]
        try:
            from app.voice.audio_io import list_input_devices
            devices += list_input_devices()
        except Exception:
            pass
        self._mic_cb = ttk.Combobox(mic_row, textvariable=self._mic_var,
                                    values=devices, width=50, state="readonly")
        self._mic_cb.pack(side=tk.LEFT)
        self._mic_cb.bind("<<ComboboxSelected>>", lambda e: self._stop_mic_test())
        self._mic_test_btn = ttk.Button(mic_row, text="Test Mic", command=self._toggle_mic_test)
        self._mic_test_btn.pack(side=tk.LEFT, padx=6)
        self._mic_level_var = tk.StringVar(value="")
        tk.Label(outer, textvariable=self._mic_level_var, font=("Segoe UI", 10),
                 foreground="#16a34a", anchor="w").grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=8)

        # Speaker (output device) + beep test
        tk.Label(outer, text="Speaker / Headphones", font=("Segoe UI", 10, "bold")).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(12, 4))
        spk_row = tk.Frame(outer)
        spk_row.grid(row=8, column=0, columnspan=2, sticky="ew", padx=8)
        self._spk_var = tk.StringVar(value="(system default)")
        out_devices = ["(system default)"]
        try:
            from app.voice.audio_io import list_output_devices
            out_devices += list_output_devices()
        except Exception:
            pass
        self._spk_cb = ttk.Combobox(spk_row, textvariable=self._spk_var,
                                    values=out_devices, width=50, state="readonly")
        self._spk_cb.pack(side=tk.LEFT)
        ttk.Button(spk_row, text="Test Speaker", command=self._test_speaker).pack(side=tk.LEFT, padx=6)
        tk.Label(outer, text="Tip: with a Bluetooth headset, pick its 'Hands-Free' output if the normal one is silent during sessions.",
                 font=("Segoe UI", 8), foreground="#6b7280", wraplength=420, justify=tk.LEFT).grid(
            row=9, column=0, columnspan=2, sticky="w", padx=8)

        ttk.Separator(outer, orient=tk.HORIZONTAL).grid(row=10, column=0, columnspan=2, sticky="ew", pady=12)

        # API keys
        tk.Label(outer, text="API Keys", font=("Segoe UI", 10, "bold")).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(0, 4))
        tk.Label(outer, text="Keys set in .env file take precedence.",
                 font=("Segoe UI", 9), foreground="#6b7280").grid(row=12, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._key_vars: dict[str, tk.StringVar] = {}
        for row_offset, (key_name, label) in enumerate([
            ("GEMINI_API_KEY", "Gemini API Key"),
            ("ANTHROPIC_API_KEY", "Anthropic API Key"),
            ("OPENAI_API_KEY", "OpenAI API Key"),
        ]):
            tk.Label(outer, text=label, font=("Segoe UI", 10)).grid(
                row=13 + row_offset, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar()
            self._key_vars[key_name] = var
            entry = tk.Entry(outer, textvariable=var, width=34, show="•", font=("Segoe UI", 10))
            entry.grid(row=13 + row_offset, column=1, sticky="ew", pady=3)

        ttk.Separator(outer, orient=tk.HORIZONTAL).grid(row=16, column=0, columnspan=2, sticky="ew", pady=12)

        # Export settings
        tk.Label(outer, text="Export Settings", font=("Segoe UI", 10, "bold")).grid(
            row=17, column=0, columnspan=2, sticky="w", pady=(0, 4))

        tk.Label(outer, text="Docx export folder:", font=("Segoe UI", 10)).grid(
            row=18, column=0, sticky="w", padx=8, pady=3)
        self._docx_dir_var = tk.StringVar()
        docx_row = tk.Frame(outer)
        docx_row.grid(row=18, column=1, sticky="ew")
        tk.Entry(docx_row, textvariable=self._docx_dir_var, width=26, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        ttk.Button(docx_row, text="Browse…", command=self._browse_docx_dir).pack(side=tk.LEFT, padx=4)

        tk.Label(outer, text="Auto-save Docx:", font=("Segoe UI", 10)).grid(
            row=19, column=0, sticky="w", padx=8, pady=3)
        self._auto_save_var = tk.BooleanVar()
        ttk.Checkbutton(outer, variable=self._auto_save_var).grid(row=19, column=1, sticky="w")

        tk.Label(outer, text="Student SOAP Note:", font=("Segoe UI", 10)).grid(
            row=20, column=0, sticky="w", padx=8, pady=3)
        self._student_soap_var = tk.BooleanVar()
        ttk.Checkbutton(outer, variable=self._student_soap_var, text="Require typing SOAP note after session").grid(row=20, column=1, sticky="w")

        tk.Label(outer, text="Backup folder:", font=("Segoe UI", 10)).grid(
            row=21, column=0, sticky="w", padx=8, pady=3)
        self._backup_dir_var = tk.StringVar()
        backup_row = tk.Frame(outer)
        backup_row.grid(row=21, column=1, sticky="ew")
        tk.Entry(backup_row, textvariable=self._backup_dir_var, width=26, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        ttk.Button(backup_row, text="Browse…", command=self._browse_backup_dir).pack(side=tk.LEFT, padx=4)

        outer.columnconfigure(1, weight=1)

    # ── Mic test ─────────────────────────────────────────────────────────────

    _BARS = "▁▂▃▄▅▆▇█"
    _BAR_THRESHOLDS = (50, 100, 200, 400, 800, 1600, 3200)

    def _toggle_mic_test(self) -> None:
        if self._test_capture is not None:
            self._stop_mic_test()
            return
        try:
            from app.voice.audio_io import AudioCapture, resolve_input_device
            name = self._mic_var.get()
            device = resolve_input_device("" if name == "(system default)" else name)
            self._test_capture = AudioCapture(self._on_test_chunk, 16000, device=device)
            self._test_capture.start()
        except Exception as exc:
            self._test_capture = None
            self._mic_level_var.set(f"Mic test failed: {exc}")
            return
        self._mic_test_btn.config(text="Stop Test")
        self._poll_test_level()

    def _on_test_chunk(self, data: bytes) -> None:  # PortAudio thread
        import array
        samples = array.array("h")
        samples.frombytes(data[: len(data) - (len(data) % 2)])
        if samples:
            self._test_level = (sum(s * s for s in samples) / len(samples)) ** 0.5

    def _poll_test_level(self) -> None:
        if self._test_capture is None:
            return
        lvl = self._test_level
        idx = sum(1 for t in self._BAR_THRESHOLDS if lvl >= t)
        verdict = "— speak now…" if lvl < 100 else "✓ picking up your voice"
        self._mic_level_var.set(f"Input level: {self._BARS[idx]}  ({lvl:.0f})  {verdict}")
        self.win.after(100, self._poll_test_level)

    def _test_speaker(self) -> None:
        """Play a short beep through the selected output device."""
        import array, math
        try:
            from app.voice.audio_io import AudioPlayer, resolve_output_device
            name = self._spk_var.get()
            device = resolve_output_device("" if name == "(system default)" else name)
            if getattr(self, "_beep_player", None) is not None:
                self._beep_player.stop()
            rate = 24000
            self._beep_player = AudioPlayer(rate, device=device)
            self._beep_player.start()
            tone = array.array("h", (
                int(11000 * math.sin(2 * math.pi * 440 * i / rate))
                for i in range(int(rate * 0.8))
            )).tobytes()
            self._beep_player.play(tone)
            self.win.after(1500, self._stop_beep)
        except Exception as exc:
            messagebox.showwarning("Test Speaker", f"Could not play test tone:\n{exc}")

    def _stop_beep(self) -> None:
        if getattr(self, "_beep_player", None) is not None:
            self._beep_player.stop()
            self._beep_player = None

    def _stop_mic_test(self) -> None:
        if self._test_capture is not None:
            self._test_capture.stop()
            self._test_capture = None
        if hasattr(self, "_mic_test_btn"):
            self._mic_test_btn.config(text="Test Mic")
            self._mic_level_var.set("")

    def _on_close(self) -> None:
        self._stop_mic_test()
        self._stop_beep()
        self.win.destroy()

    def _load_settings(self) -> None:
        self._backend_var.set(get_setting("voice_backend", "gemini"))
        self._feedback_var.set(get_setting("feedback_backend", "claude"))
        saved_mic = get_setting("input_device", "")
        if saved_mic and saved_mic in self._mic_cb["values"]:
            self._mic_var.set(saved_mic)
        saved_spk = get_setting("output_device", "")
        if saved_spk and saved_spk in self._spk_cb["values"]:
            self._spk_var.set(saved_spk)
        self._docx_dir_var.set(get_setting("docx_export_dir", ""))
        self._auto_save_var.set(get_setting("auto_save_docx", "false") == "true")
        self._student_soap_var.set(get_setting("student_soap_note_typing", "false") == "true")
        self._backup_dir_var.set(get_setting("backup_dir", ""))
        # Load API keys from env (masked)
        import os as _os
        for key_name in self._key_vars:
            env_val = _os.environ.get(key_name, "")
            self._key_vars[key_name].set(env_val)

    def _browse_docx_dir(self) -> None:
        d = filedialog.askdirectory(title="Select Docx Export Folder")
        if d:
            self._docx_dir_var.set(d)

    def _browse_backup_dir(self) -> None:
        d = filedialog.askdirectory(title="Select Backup Folder")
        if d:
            self._backup_dir_var.set(d)

    def _save(self) -> None:
        self._stop_mic_test()
        set_setting("voice_backend", self._backend_var.get())
        set_setting("feedback_backend", self._feedback_var.get())
        mic = self._mic_var.get()
        set_setting("input_device", "" if mic == "(system default)" else mic)
        spk = self._spk_var.get()
        set_setting("output_device", "" if spk == "(system default)" else spk)
        set_setting("docx_export_dir", self._docx_dir_var.get())
        set_setting("auto_save_docx", "true" if self._auto_save_var.get() else "false")
        set_setting("student_soap_note_typing", "true" if self._student_soap_var.get() else "false")
        set_setting("backup_dir", self._backup_dir_var.get())

        # Update API keys in the running process and persist them to .env so
        # they survive a restart.
        import os as _os
        changed_keys = {}
        for key_name, var in self._key_vars.items():
            val = var.get().strip()
            if val and val != _os.environ.get(key_name, ""):
                _os.environ[key_name] = val
                changed_keys[key_name] = val

        if changed_keys:
            self._persist_keys_to_env(changed_keys)

        messagebox.showinfo("Preferences", "Settings saved.")
        self.win.destroy()

    @staticmethod
    def _persist_keys_to_env(keys: dict) -> None:
        """Write/update the given KEY=value pairs in the app-managed .env file,
        preserving any unrelated lines already present."""
        import config

        lines: list[str] = []
        if os.path.exists(config.ENV_PATH):
            try:
                with open(config.ENV_PATH, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except OSError:
                lines = []

        remaining = dict(keys)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name = stripped.split("=", 1)[0].strip()
            if name in remaining:
                lines[i] = f"{name}={remaining.pop(name)}"
        for name, val in remaining.items():
            lines.append(f"{name}={val}")

        try:
            os.makedirs(os.path.dirname(config.ENV_PATH), exist_ok=True)
            with open(config.ENV_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as exc:
            messagebox.showwarning(
                "Preferences",
                f"Could not write API keys to .env:\n{exc}\n\n"
                "They will work for this session only.",
            )
