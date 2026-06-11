import sqlite3
import os
import shutil
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import config

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA auto_vacuum=INCREMENTAL;

CREATE TABLE IF NOT EXISTS sessions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at               TEXT NOT NULL,
    mode                     TEXT NOT NULL,
    case_name                TEXT NOT NULL,
    case_id                  TEXT,
    eval_template            TEXT,
    voice_backend            TEXT NOT NULL,
    duration_seconds         INTEGER,
    raw_transcript           TEXT NOT NULL,
    raw_claude_response      TEXT,
    raw_case_json            TEXT NOT NULL,
    raw_eval_json            TEXT,
    grammar_score            REAL,
    medical_accuracy_score   REAL,
    clinical_reasoning_score REAL,
    professionalism_score    REAL,
    fluency_score            REAL,
    self_grammar             REAL,
    self_medical_accuracy    REAL,
    self_clinical_reasoning  REAL,
    self_professionalism     REAL,
    self_fluency             REAL,
    checklist_results        TEXT,
    history_completeness     REAL,
    ice_elicited             INTEGER,
    empathy_markers_found    TEXT,
    student_soap_note        TEXT,
    soap_note                TEXT,
    reference_soap           TEXT,
    corrections              TEXT,
    anki_cards               TEXT,
    summary_feedback         TEXT,
    debrief_chat             TEXT,
    docx_path                TEXT,

    -- Token usage and cost tracking
    claude_input_tokens      INTEGER,
    claude_output_tokens     INTEGER,
    claude_cached_tokens     INTEGER,
    claude_cost_usd          REAL,
    voice_cost_usd           REAL,
    total_cost_usd           REAL,
    cost_report_path         TEXT
);

CREATE TABLE IF NOT EXISTS app_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    level       TEXT NOT NULL,
    session_id  INTEGER,
    message     TEXT NOT NULL,
    traceback   TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "voice_backend": "gemini",
    "docx_export_dir": "",
    "auto_save_docx": "false",
    "backup_dir": "",
    "window_geometry": "",
    "student_soap_note_typing": "false",
}


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN professionalism_score REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN self_professionalism REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN student_soap_note TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN debrief_chat TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        _insert_default_settings(conn)
    finally:
        conn.close()


def _insert_default_settings(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
    conn.commit()


def seed_data_if_needed() -> None:
    """Extract bundled seed data to external data/ dir if not present."""
    if os.path.exists(config.DATA_DIR) and os.listdir(config.DATA_DIR):
        return

    seed_src = None
    if getattr(__import__("sys"), "frozen", False):
        import sys
        seed_src = os.path.join(sys._MEIPASS, "data_seed")  # type: ignore[attr-defined]

    if seed_src and os.path.exists(seed_src):
        shutil.copytree(seed_src, config.DATA_DIR, dirs_exist_ok=True)
        log_event("INFO", "Seed data extracted to data/")


def backup_db(session_id: Optional[int] = None) -> None:
    os.makedirs(config.DB_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(config.DB_BACKUP_DIR, f"sessions_{timestamp}.db")
    try:
        shutil.copy2(config.DB_PATH, dest)
        _prune_backups()
        log_event("INFO", f"DB backup created: {dest}", session_id=session_id)
    except Exception as exc:
        log_event("ERROR", f"DB backup failed: {exc}", session_id=session_id)


def _prune_backups() -> None:
    backups = sorted(
        [f for f in os.listdir(config.DB_BACKUP_DIR) if f.endswith(".db")],
        reverse=True,
    )
    for old in backups[config.MAX_DB_BACKUPS:]:
        try:
            os.remove(os.path.join(config.DB_BACKUP_DIR, old))
        except OSError:
            pass


def log_event(
    level: str,
    message: str,
    session_id: Optional[int] = None,
    traceback_str: Optional[str] = None,
) -> None:
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO app_logs (timestamp, level, session_id, message, traceback) VALUES (?,?,?,?,?)",
            (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), level, session_id, message, traceback_str),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
