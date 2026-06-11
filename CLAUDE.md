# MedVoiceTrainer

Desktop application for medical English speaking practice targeting Korean IMGs preparing for OSCE, OET, and US Internal Medicine residency match.

## Stack
- Python 3.11+ with tkinter (stdlib UI)
- `google-genai` — Gemini Live real-time voice
- `openai` — OpenAI Realtime API voice
- `anthropic` — Claude API post-session analysis
- `sounddevice` — audio I/O (NOT pyaudio/pygame)
- `python-docx`, `genanki`, `sqlite3`, `python-dotenv`, `matplotlib`

## Run
```
python main.py          # normal mode
python main.py --dev    # mock mode (no API calls, no audio hardware needed)
```

## Project layout
- `app/ui/` — all tkinter windows and tabs
- `app/voice/` — VoiceClient abstraction + Gemini/OpenAI implementations
- `app/analysis/` — Claude API feedback engine + prompt builder
- `app/export/` — docx and Anki exporters
- `app/db/` — SQLite init and typed query functions
- `data/` — cases JSON, interview banks, eval templates (EXTERNAL — lives next to exe)
- `db/` — sessions.db + backups (EXTERNAL)

## Critical constraints
- DPI fix must be at top of main.py BEFORE any tkinter import
- All tkinter updates MUST happen in main thread via `root.after(100, poll_queue)`
- Voice runs in daemon thread with its own asyncio event loop
- All paths via `config.get_base_dir()` for PyInstaller compatibility
- Never lose transcript — persist each turn to DB as it arrives

## Data flow
1. User selects case/scenario and starts session
2. VoiceClient streams audio bidirectionally in background thread
3. Events flow via `queue.Queue` to UI poll loop
4. On session end: self-assessment dialog → Claude analysis → Feedback Toplevel
5. Results saved to sessions.db; optional docx/Anki export

## Future work
- **Echo cancellation** — Microphone captures speaker output, causing the AI to hear itself. Recommend headphones for now. Real echo cancellation (WebRTC, spectral subtraction) would require passing captured audio through a DSP pipeline before sending to the API.
