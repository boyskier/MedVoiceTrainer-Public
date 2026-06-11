# MedVoiceTrainer

> **Real-time voice AI practice for medical English — OSCE, OET, and US IM residency interview preparation.**

International Medical Graduates (IMGs) and medical students preparing for clinical exams (OSCE, OET) or the US residency match often struggle to find realistic, structured spoken English practice. MedVoiceTrainer provides a desktop application that simulates real patient encounters and residency interviews using state-of-the-art voice AI, then delivers detailed, rubric-scored feedback and interactive debriefing.

---

## Features

| Feature | Details |
|---------|---------|
| **Patient Encounters** | 8 clinical cases (Cardiology × 2, GI × 2, Pulm × 2, Neuro × 2) |
| **Residency Interviews** | 11 scenarios — Behavioral, Clinical, IMG-Specific (fully customizable) |
| **Custom Scenarios** | Free-form persona + evaluation criteria |
| **Real-time Voice AI** | Gemini Live (default) or OpenAI Realtime |
| **Post-session Analysis** | Gemini (default), Claude, or OpenAI — rubric scores, SOAP note, corrections, Anki cards |
| **Interactive Debrief** | Socratic dialogue with AI Tutor (pluggable: Gemini, Claude, or OpenAI) |
| **Self-assessment** | Sliders before feedback; delta shown against AI score |
| **High-DPI & Local Time** | Automatic local time zone conversion and DPI-scaled layout configurations |
| **Anki Export** | `.apkg` export for spaced repetition study |
| **Word Report** | `.docx` session report with full analysis |
| **API Cost Report** | Automatic `.txt` cost report after every session |
| **Dev Mode** | Full UI walkthrough without any API keys or microphone |

---

## Quick Start

### Prerequisites

- Python 3.11+
- API Keys: [Google Gemini](https://aistudio.google.com) (**Required** — you only need a single Gemini API key to run both real-time voice and post-session feedback analysis).
- Optional API Keys: [Anthropic Claude](https://console.anthropic.com) (for post-session feedback analysis) and [OpenAI](https://platform.openai.com) (for both voice and feedback analysis).

### Install and build

```bat
REM Windows — double-click or run in terminal:
build.bat
```

This installs dependencies, runs tests, builds the `.exe` via PyInstaller, and launches it.

### Run from source

```bash
pip install -r requirements.txt
python main.py
```

### Dev mode (no API keys needed)

```bash
python main.py --dev
```

### Configure API keys

Edit `.env` in the project root (or in `dist/MedVoiceTrainer/` after building):

```env
GEMINI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...  # optional (for Claude post-session analysis)
OPENAI_API_KEY=sk-...         # optional (for OpenAI voice or post-session analysis)
```

---

## Project Structure

```
MedVoiceTrainer/
├── main.py                    # Entry point; --dev flag
├── config.py                  # Paths (PyInstaller-safe via get_base_dir())
├── build.bat                  # One-click build script
├── requirements.txt
├── .env                       # API keys (not committed)
├── USER_GUIDE_KO.md           # Korean user guide for med students
│
├── app/
│   ├── ui/                    # All tkinter windows and tabs
│   │   ├── main_window.py
│   │   ├── session_base.py    # Shared session lifecycle, queue polling
│   │   ├── encounter_tab.py
│   │   ├── interview_tab.py
│   │   ├── custom_tab.py
│   │   ├── history_tab.py
│   │   ├── feedback_window.py
│   │   └── preferences_window.py
│   ├── voice/                 # Voice client abstraction
│   │   ├── base_client.py     # ABC — VoiceClient
│   │   ├── gemini_client.py   # Gemini Live 2.0
│   │   ├── openai_client.py   # OpenAI Realtime gpt-4o
│   │   ├── mock_client.py     # Dev mode mock
│   │   └── factory.py
│   ├── analysis/              # Post-session intelligence
│   │   ├── prompt_builder.py  # Dynamic prompt assembly
│   │   ├── feedback_engine.py # Claude API call + cost integration
│   │   └── cost_tracker.py    # Token counting, cost computation, report
│   ├── export/
│   │   ├── docx_exporter.py
│   │   └── anki_exporter.py
│   └── db/
│       ├── database.py        # SQLite init, WAL, backup
│       └── queries.py         # Typed SQL functions
│
├── data/                      # External — lives next to exe, user-editable
│   ├── cases/{cardio,gi,pulm,neuro}/*.json
│   ├── interview_banks/behavioral.json
│   ├── interview_banks/img_specific.json
│   ├── eval/*.json            # 5 evaluation templates
│   └── custom/                # User-created scenarios
│
├── db/
│   ├── sessions.db            # Auto-created
│   ├── backups/               # Auto-backup after each session
│   └── cost_reports/          # API cost reports (.txt)
│
└── tests/                     # 197 unit tests, 100% pass
    ├── test_config.py
    ├── test_database.py
    ├── test_prompt_builder.py
    ├── test_feedback_engine.py
    ├── test_voice_clients.py
    ├── test_exporters.py
    ├── test_data_files.py
    └── test_cost_tracker.py
```

---

## Architecture

### Threading model

Voice AI runs in a daemon thread with its own asyncio event loop. The UI thread polls a `queue.Queue` every 100ms via `root.after(100, poll_queue)`. This ensures tkinter is never touched from the audio thread.

```
[Microphone] → [sounddevice] → [VoiceClient (daemon thread, asyncio)]
                                        ↓ queue.Queue events
                              [UI poll loop (main thread)]
                                        ↓
                              [transcript display, timer, status]
```

### Session lifecycle

```
Start → create_session(DB) → VoiceClient.connect() → stream audio
                                                    ↓
                                          append_turn(DB) per turn
                                                    ↓
End & Analyze → self-assessment dialog
             → feedback_engine.run_analysis() [Claude API]
             → finalize_session(DB) + backup_db()
             → cost_tracker → cost_report.txt
             → FeedbackWindow (5 tabs)
```

### Evaluation pipeline

```
Transcript + Case JSON + Eval Template JSON
        ↓ prompt_builder.build_analysis_prompt()
Claude claude-sonnet-4-6 (max 4096 tokens output)
        ↓ JSON response
Parsed: scores, checklist, SOAP, corrections, Anki cards, summary
        ↓
Saved to sessions.db + rendered in FeedbackWindow
```

---

## Adding Custom Cases

Create a JSON file in `data/cases/{system}/`:

```json
{
  "id": "cardio_003",
  "system": "cardiology",
  "difficulty": "advanced",
  "eval_template": "history_taking",
  "patient_name": "Mrs. Lee",
  "age": 65,
  "gender": "female",
  "chief_complaint": "palpitations and dizziness",
  "hpi_details": "...",
  "ideas": "...",
  "concerns": "...",
  "expectations": "...",
  "pmh": "...",
  "medications": "...",
  "social_hx": "...",
  "reference_soap": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." },
  "learning_objectives": ["..."]
}
```

Restart the app — the new case appears immediately in the dropdown.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

197 tests covering: config, database CRUD, prompt builder, feedback engine (mocked API), voice client abstraction, exporters (docx + anki), data file validation, and cost tracker.

---

## Cost Estimates

| Component | Pricing | 5-min session |
|-----------|---------|---------------|
| **Gemini (analysis)** | $0.075/1M input + $0.30/1M output | **<$0.001** (Fraction of a cent!) |
| Claude (analysis) | $3/1M input + $15/1M output | ~$0.02–0.05 |
| **Gemini Live (voice)** | ~$0.50/1M audio tokens | ~$0.0005 |
| OpenAI Realtime (voice) | $100/1M audio input + $200/1M output | ~$0.10–0.20 |

> 💡 **Recommendation:** Running the entire app using Google Gemini (for both voice and post-session analysis) is the most cost-efficient and simplest setup, costing less than **$0.001** per session.

---

## Customizing for Your Home Country

While MedVoiceTrainer was originally developed with a focus on International Medical Graduates (IMGs) from specific countries, it is designed to be completely country-agnostic and fully customizable:

1. **Customizing Interview Scenarios**:
   You can easily edit the interview questions and scenarios to match your specific country's context by editing the JSON files in:
   - [data/interview_banks/behavioral.json](data/interview_banks/behavioral.json)
   - [data/interview_banks/img_specific.json](data/interview_banks/img_specific.json)
   
   Simply modify the program names, PD names, or the questions (e.g. changing any specific country references to your own home country).

2. **Customizing Cases**:
   All patient clinical cases are defined as JSON files in [data/cases/](data/cases/). You can copy an existing JSON file, modify its details (chief complaint, history, expectations, etc.), save it, and restart the app. It will appear in the UI dropdown immediately.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
