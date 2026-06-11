"""Tests for app/db/database.py and app/db/queries.py."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import builtins
from unittest.mock import patch, MagicMock


class TestDatabaseInit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_sessions.db")
        self.backup_dir = os.path.join(self.tmpdir, "backups")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patched_init(self):
        """Patch config to use temp DB path."""
        import config as cfg
        with patch.object(cfg, "DB_PATH", self.db_path), \
             patch.object(cfg, "DB_BACKUP_DIR", self.backup_dir):
            from app.db import database
            database.init_db()
        return self.db_path

    def test_creates_db_file(self):
        self._patched_init()
        self.assertTrue(os.path.exists(self.db_path))

    def test_sessions_table_exists(self):
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    def test_settings_table_exists(self):
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    def test_app_logs_table_exists(self):
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_logs'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    def test_default_settings_inserted(self):
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
        conn.close()
        self.assertIn("voice_backend", rows)
        self.assertEqual(rows["voice_backend"], "gemini")
        self.assertIn("auto_save_docx", rows)
        self.assertEqual(rows["auto_save_docx"], "false")

    def test_wal_mode_enabled(self):
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode, "wal")

    def test_init_is_idempotent(self):
        """Running init twice should not raise or duplicate default settings."""
        self._patched_init()
        self._patched_init()
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM settings WHERE key='voice_backend'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)


class TestQueriesWithTempDB(unittest.TestCase):
    """Integration tests for queries.py against a real SQLite temp DB."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.backup_dir = os.path.join(self.tmpdir, "backups")
        import config as cfg
        self._orig_db = cfg.DB_PATH
        self._orig_backup = cfg.DB_BACKUP_DIR
        cfg.DB_PATH = self.db_path
        cfg.DB_BACKUP_DIR = self.backup_dir

        from app.db.database import SCHEMA_SQL, DEFAULT_SETTINGS, _insert_default_settings
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        _insert_default_settings(conn)
        conn.close()

    def tearDown(self):
        import config as cfg
        cfg.DB_PATH = self._orig_db
        cfg.DB_BACKUP_DIR = self._orig_backup
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── settings ──────────────────────────────────────────────────────────────

    def test_get_setting_default(self):
        from app.db.queries import get_setting
        val = get_setting("voice_backend")
        self.assertEqual(val, "gemini")

    def test_get_setting_missing_key_returns_default(self):
        from app.db.queries import get_setting
        val = get_setting("nonexistent_key", default="fallback")
        self.assertEqual(val, "fallback")

    def test_set_and_get_setting(self):
        from app.db.queries import get_setting, set_setting
        set_setting("voice_backend", "openai")
        self.assertEqual(get_setting("voice_backend"), "openai")

    def test_set_setting_overwrite(self):
        from app.db.queries import get_setting, set_setting
        set_setting("test_key", "value1")
        set_setting("test_key", "value2")
        self.assertEqual(get_setting("test_key"), "value2")

    # ── session CRUD ──────────────────────────────────────────────────────────

    def _make_session(self):
        from app.db.queries import create_session
        return create_session(
            mode="encounter",
            case_name="Mr. Test",
            case_id="cardio_001",
            eval_template="history_taking",
            voice_backend="mock",
            raw_case_json={"id": "cardio_001", "chief_complaint": "chest pain"},
            raw_eval_json={"name": "History Taking"},
        )

    def test_create_session_returns_int_id(self):
        sid = self._make_session()
        self.assertIsInstance(sid, int)
        self.assertGreater(sid, 0)

    def test_create_session_persisted(self):
        from app.db.queries import get_session
        sid = self._make_session()
        row = get_session(sid)
        self.assertIsNotNone(row)
        self.assertEqual(row["mode"], "encounter")
        self.assertEqual(row["case_name"], "Mr. Test")
        self.assertEqual(row["voice_backend"], "mock")

    def test_create_session_raw_transcript_is_empty_list(self):
        from app.db.queries import get_session
        sid = self._make_session()
        row = get_session(sid)
        self.assertEqual(json.loads(row["raw_transcript"]), [])

    def test_append_turn_persists_immediately(self):
        from app.db.queries import create_session, append_turn, get_session
        sid = self._make_session()
        turn = {"turn_index": 0, "role": "patient", "text": "Hello doctor"}
        append_turn(sid, turn)
        row = get_session(sid)
        transcript = json.loads(row["raw_transcript"])
        self.assertEqual(len(transcript), 1)
        self.assertEqual(transcript[0]["text"], "Hello doctor")

    def test_append_multiple_turns_in_order(self):
        from app.db.queries import create_session, append_turn, get_session
        sid = self._make_session()
        for i in range(5):
            append_turn(sid, {"turn_index": i, "role": "user" if i % 2 else "patient", "text": f"Turn {i}"})
        row = get_session(sid)
        transcript = json.loads(row["raw_transcript"])
        self.assertEqual(len(transcript), 5)
        for i, turn in enumerate(transcript):
            self.assertEqual(turn["turn_index"], i)

    def test_finalize_session_writes_scores(self):
        from app.db.queries import finalize_session, get_session
        sid = self._make_session()
        analysis = {
            "overall_scores": {
                "grammar": 7.5, "medical_accuracy": 8.0,
                "clinical_reasoning": 6.5, "communication_fluency": 7.0,
            },
            "summary_feedback": "Good work.",
            "checklist_results": [],
            "corrections": [],
            "anki_cards": [],
        }
        finalize_session(sid, duration_seconds=120, analysis=analysis)
        row = get_session(sid)
        self.assertAlmostEqual(row["grammar_score"], 7.5)
        self.assertAlmostEqual(row["medical_accuracy_score"], 8.0)
        self.assertAlmostEqual(row["clinical_reasoning_score"], 6.5)
        self.assertAlmostEqual(row["fluency_score"], 7.0)
        self.assertEqual(row["duration_seconds"], 120)
        self.assertEqual(row["summary_feedback"], "Good work.")

    def test_finalize_session_stores_raw_claude_response(self):
        from app.db.queries import finalize_session, get_session
        sid = self._make_session()
        analysis = {"overall_scores": {}, "summary_feedback": "test"}
        finalize_session(sid, 60, analysis)
        row = get_session(sid)
        stored = json.loads(row["raw_claude_response"])
        self.assertEqual(stored["summary_feedback"], "test")

    def test_finalize_session_handles_missing_values(self):
        from app.db.queries import finalize_session, get_session
        sid = self._make_session()
        analysis = {"summary_feedback": "test"}
        finalize_session(sid, 60, analysis)
        row = get_session(sid)
        self.assertIsNone(row["grammar_score"])
        self.assertIsNone(row["checklist_results"])
        self.assertIsNone(row["empathy_markers_found"])
        self.assertIsNone(row["corrections"])
        self.assertIsNone(row["anki_cards"])

    def test_finalize_session_ice_elicited_null_when_absent(self):
        # An eval without an ICE section (e.g. interview) must store NULL,
        # not 0 ("failed to elicit ICE").
        from app.db.queries import finalize_session, get_session
        sid = self._make_session()
        finalize_session(sid, 60, {"summary_feedback": "test"})
        row = get_session(sid)
        self.assertIsNone(row["ice_elicited"])

    def test_finalize_session_ice_elicited_true_false(self):
        from app.db.queries import finalize_session, get_session
        sid = self._make_session()
        finalize_session(sid, 60, {"ice_elicited": True})
        self.assertEqual(get_session(sid)["ice_elicited"], 1)
        sid2 = self._make_session()
        finalize_session(sid2, 60, {"ice_elicited": False})
        self.assertEqual(get_session(sid2)["ice_elicited"], 0)

    def test_save_self_scores(self):
        from app.db.queries import save_self_scores, get_session
        sid = self._make_session()
        save_self_scores(sid, {
            "grammar": 6.0, "medical_accuracy": 5.5,
            "clinical_reasoning": 7.0, "professionalism": 8.5,
            "communication_fluency": 6.5,
        })
        row = get_session(sid)
        self.assertAlmostEqual(row["self_grammar"], 6.0)
        self.assertAlmostEqual(row["self_medical_accuracy"], 5.5)
        self.assertAlmostEqual(row["self_clinical_reasoning"], 7.0)
        self.assertAlmostEqual(row["self_professionalism"], 8.5)
        self.assertAlmostEqual(row["self_fluency"], 6.5)

    def test_list_sessions_returns_list(self):
        from app.db.queries import list_sessions
        self._make_session()
        self._make_session()
        sessions = list_sessions()
        self.assertIsInstance(sessions, list)
        self.assertGreaterEqual(len(sessions), 2)

    def test_list_sessions_ordered_newest_first(self):
        from app.db.queries import list_sessions, create_session
        import time
        create_session("encounter", "Old Case", None, None, "mock", {}, None)
        time.sleep(0.01)
        create_session("encounter", "New Case", None, None, "mock", {}, None)
        sessions = list_sessions()
        self.assertEqual(sessions[0]["case_name"], "New Case")

    def test_delete_session(self):
        from app.db.queries import delete_session, get_session
        sid = self._make_session()
        delete_session(sid)
        row = get_session(sid)
        self.assertIsNone(row)

    def test_get_sessions_for_case(self):
        from app.db.queries import create_session, get_sessions_for_case
        create_session("encounter", "Case A", "cardio_001", None, "mock", {}, None)
        create_session("encounter", "Case A", "cardio_001", None, "mock", {}, None)
        create_session("encounter", "Case B", "gi_001", None, "mock", {}, None)
        results = get_sessions_for_case("cardio_001")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["case_id"], "cardio_001")

    def test_save_docx_path(self):
        from app.db.queries import save_docx_path, get_session
        sid = self._make_session()
        save_docx_path(sid, "/some/path/report.docx")
        row = get_session(sid)
        self.assertEqual(row["docx_path"], "/some/path/report.docx")

    def test_save_cost_data(self):
        from app.db.queries import save_cost_data, get_session
        sid = self._make_session()
        save_cost_data(
            sid,
            claude_input=1200,
            claude_output=350,
            claude_cached=1000,
            claude_cost=0.0035,
            voice_cost=0.0015,
            total_cost=0.0050,
            report_path="/path/to/report.txt"
        )
        row = get_session(sid)
        self.assertEqual(row["claude_input_tokens"], 1200)
        self.assertEqual(row["claude_output_tokens"], 350)
        self.assertEqual(row["claude_cached_tokens"], 1000)
        self.assertAlmostEqual(row["claude_cost_usd"], 0.0035)
        self.assertAlmostEqual(row["voice_cost_usd"], 0.0015)
        self.assertAlmostEqual(row["total_cost_usd"], 0.0050)
        self.assertEqual(row["cost_report_path"], "/path/to/report.txt")

    def test_save_student_soap(self):
        from app.db.queries import save_student_soap, get_session
        sid = self._make_session()
        soap = json.dumps({"s": "Subjective part", "o": "Objective part"})
        save_student_soap(sid, soap)
        row = get_session(sid)
        self.assertEqual(row["student_soap_note"], soap)

    def test_save_debrief_chat(self):
        from app.db.queries import save_debrief_chat, get_session
        sid = self._make_session()
        chat = json.dumps([{"role": "user", "text": "What about my grammar?"}])
        save_debrief_chat(sid, chat)
        row = get_session(sid)
        self.assertEqual(row["debrief_chat"], chat)


class TestDatabaseBackup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "sessions.db")
        self.backup_dir = os.path.join(self.tmpdir, "backups")
        # Create a minimal DB file
        conn = sqlite3.connect(self.db_path)
        conn.close()
        import config as cfg
        self._orig_db = cfg.DB_PATH
        self._orig_backup = cfg.DB_BACKUP_DIR
        cfg.DB_PATH = self.db_path
        cfg.DB_BACKUP_DIR = self.backup_dir

    def tearDown(self):
        import config as cfg
        cfg.DB_PATH = self._orig_db
        cfg.DB_BACKUP_DIR = self._orig_backup
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_backup_creates_file(self):
        from app.db.database import backup_db
        backup_db()
        files = os.listdir(self.backup_dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("sessions_"))
        self.assertTrue(files[0].endswith(".db"))

    def test_backup_prunes_to_max(self):
        """Manually create 5 backup files then call _prune_backups to verify pruning."""
        import config
        from app.db.database import _prune_backups
        original_max = config.MAX_DB_BACKUPS
        config.MAX_DB_BACKUPS = 3
        os.makedirs(self.backup_dir, exist_ok=True)
        try:
            for i in range(5):
                path = os.path.join(self.backup_dir, f"sessions_2026060{i}_120000.db")
                with open(path, "w") as f:
                    f.write("x")
            _prune_backups()
            files = os.listdir(self.backup_dir)
            self.assertEqual(len(files), 3)
        finally:
            config.MAX_DB_BACKUPS = original_max

    def test_log_event_writes_to_db(self):
        from app.db.database import SCHEMA_SQL, _insert_default_settings, log_event
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        _insert_default_settings(conn)
        conn.close()
        log_event("INFO", "test message", session_id=None)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM app_logs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["message"], "test message")
        self.assertEqual(row["level"], "INFO")

    def test_backup_handles_shutil_error(self):
        from app.db.database import backup_db
        with patch("shutil.copy2", side_effect=Exception("copy error")):
            # Should catch exception and log it, not raise
            backup_db(session_id=1)

    def test_prune_backups_handles_os_error(self):
        from app.db.database import _prune_backups
        import config
        original_max = config.MAX_DB_BACKUPS
        config.MAX_DB_BACKUPS = 0
        os.makedirs(self.backup_dir, exist_ok=True)
        path = os.path.join(self.backup_dir, "sessions_test.db")
        with open(path, "w") as f:
            f.write("x")
        with patch("os.remove", side_effect=OSError("locked")):
            # Should pass silently
            _prune_backups()
        config.MAX_DB_BACKUPS = original_max

class TestSeedData(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import config
        self.orig_data_dir = config.DATA_DIR
        config.DATA_DIR = os.path.join(self.tmpdir, "data")
        
    def tearDown(self):
        import config
        config.DATA_DIR = self.orig_data_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        
    def test_seed_data_does_nothing_if_dir_exists_and_populated(self):
        import config
        from app.db.database import seed_data_if_needed
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(os.path.join(config.DATA_DIR, "dummy.txt"), "w") as f:
            f.write("test")
        with patch("shutil.copytree") as mock_copy:
            seed_data_if_needed()
            mock_copy.assert_not_called()

    def test_seed_data_frozen_sys(self):
        from app.db.database import seed_data_if_needed
        # Mock sys._MEIPASS logic
        class MockSys:
            frozen = True
            _MEIPASS = self.tmpdir
            
        import config
        with patch("os.listdir", return_value=[]), \
             patch("builtins.__import__") as mock_import, \
             patch("shutil.copytree") as mock_copy, \
             patch("os.path.exists", return_value=True):
            
            mock_sys = MagicMock()
            mock_sys._MEIPASS = "/mock/path"
            mock_sys.frozen = True
            mock_import.return_value = mock_sys
            
            # Use patch.object to mock sys.frozen
            import sys
            with patch.object(sys, "frozen", True, create=True):
                seed_data_if_needed()
                mock_copy.assert_called_once()

if __name__ == "__main__":
    unittest.main()

