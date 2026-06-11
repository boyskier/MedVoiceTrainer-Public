import sys
import os

def get_base_dir() -> str:
    """Returns directory containing the exe (frozen) or this file (dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
ENV_PATH = os.path.join(BASE_DIR, ".env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "db", "sessions.db")
DB_BACKUP_DIR = os.path.join(BASE_DIR, "db", "backups")

CASES_DIR = os.path.join(DATA_DIR, "cases")
INTERVIEW_BANKS_DIR = os.path.join(DATA_DIR, "interview_banks")
EVAL_DIR = os.path.join(DATA_DIR, "eval")
CUSTOM_DIR = os.path.join(DATA_DIR, "custom")
FOUNDATIONS_PHRASES_PATH = os.path.join(DATA_DIR, "foundations_phrases.json")

CASE_SYSTEMS = ["foundations", "drills", "cardio", "gi", "pulm", "neuro"]

APP_TITLE = "MedVoiceTrainer"
WINDOW_SIZE = "920x680"
FEEDBACK_WINDOW_SIZE = "820x620"
PREFS_WINDOW_SIZE = "480x360"

QUEUE_POLL_MS = 100
MAX_DB_BACKUPS = 20

VOICE_BACKENDS = ["gemini", "openai"]
DEFAULT_VOICE_BACKEND = "gemini"

# Post-session analysis (feedback) can run on any of these providers — the user
# only needs the one API key they already have. Real-time voice is unaffected.
FEEDBACK_BACKENDS = ["gemini", "claude", "openai"]
DEFAULT_FEEDBACK_BACKEND = "gemini"
