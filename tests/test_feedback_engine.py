"""Tests for app/analysis/feedback_engine.py."""
import json
import unittest
from unittest.mock import MagicMock, patch

SAMPLE_TRANSCRIPT = [
    {"turn_index": 0, "role": "patient", "text": "I have chest pain."},
    {"turn_index": 1, "role": "user", "text": "When did it start?"},
]

SAMPLE_CASE = {"id": "cardio_001", "chief_complaint": "chest pain"}
SAMPLE_EVAL = {
    "name": "History Taking",
    "output_sections": ["scores", "corrections", "anki_cards", "summary"],
    "metrics": {"grammar": {"label": "Grammar", "anchors": {}}},
    "checklist": [],
    "empathy_markers": [],
}

VALID_ANALYSIS_JSON = {
    "overall_scores": {"grammar": 7.5, "medical_accuracy": 8.0, "clinical_reasoning": 6.5, "communication_fluency": 7.0},
    "corrections": [],
    "anki_cards": [{"front": "Q", "back": "A", "tags": ["medical-english"]}],
    "summary_feedback": "Good work overall.",
}


class TestMockAnalysisEngine(unittest.TestCase):
    def test_returns_dict(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIsInstance(result, dict)

    def test_contains_overall_scores(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("overall_scores", result)
        scores = result["overall_scores"]
        self.assertIsInstance(scores, dict)
        self.assertTrue(len(scores) > 0)

    def test_scores_are_floats_in_range(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        for k, v in result["overall_scores"].items():
            self.assertIsInstance(v, float, f"Score {k} is not float: {v}")
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 10.0)

    def test_contains_summary_feedback(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("summary_feedback", result)
        self.assertIsInstance(result["summary_feedback"], str)
        self.assertTrue(len(result["summary_feedback"]) > 10)

    def test_contains_anki_cards_list(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("anki_cards", result)
        self.assertIsInstance(result["anki_cards"], list)
        self.assertGreater(len(result["anki_cards"]), 0)

    def test_anki_card_structure(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        for card in result["anki_cards"]:
            self.assertIn("front", card)
            self.assertIn("back", card)
            self.assertIn("tags", card)
            self.assertIsInstance(card["tags"], list)

    def test_with_self_scores_computes_delta(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        self_scores = {"grammar": 5.0, "medical_accuracy": 5.0, "clinical_reasoning": 5.0, "communication_fluency": 5.0}
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, self_scores=self_scores)
        self.assertIn("self_assessment_delta", result)
        delta = result["self_assessment_delta"]
        for k, v in delta.items():
            self.assertIsInstance(v, float)

    def test_without_self_scores_no_delta(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, self_scores=None)
        self.assertNotIn("self_assessment_delta", result)

    def test_contains_corrections_list(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("corrections", result)
        self.assertIsInstance(result["corrections"], list)

    def test_correction_structure(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        for corr in result["corrections"]:
            self.assertIn("turn_index", corr)
            self.assertIn("original", corr)
            self.assertIn("corrected", corr)
            self.assertIn("explanation", corr)

    def test_result_is_deep_copy(self):
        """Modifying result should not affect subsequent calls."""
        from app.analysis.feedback_engine import MockAnalysisEngine
        r1 = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        r1["overall_scores"]["grammar"] = 0.0
        r2 = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertNotEqual(r2["overall_scores"]["grammar"], 0.0)

    def test_soap_note_present_in_mock(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("soap_note", result)
        soap = result["soap_note"]
        for key in ("subjective", "objective", "assessment", "plan"):
            self.assertIn(key, soap)
            self.assertIsInstance(soap[key], str)


class TestRunAnalysisAPIIntegration(unittest.TestCase):
    """Test run_analysis() with mocked Anthropic client (no real API call)."""

    def setUp(self):
        # Pin the backend to Claude: these tests mock anthropic, and must not
        # be steered to another provider by whatever feedback_backend the
        # user's real settings DB currently holds.
        patcher = patch(
            "app.analysis.feedback_engine._resolve_feedback_backend",
            return_value="claude",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_json_response_is_parsed(self):
        from app.analysis.feedback_engine import run_analysis
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(VALID_ANALYSIS_JSON))]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.return_value = mock_message
                result = run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertEqual(result["summary_feedback"], "Good work overall.")

    def test_robust_json_extraction(self):
        from app.analysis.feedback_engine import run_analysis
        fenced = f"Here is the JSON:\n```json\n{json.dumps(VALID_ANALYSIS_JSON)}\n```\nHope it helps."
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=fenced)]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.return_value = mock_message
                result = run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("overall_scores", result)

    def test_cost_recording_in_db(self):
        from app.analysis.feedback_engine import run_analysis
        import tempfile
        import sqlite3
        import config
        import os
        from app.db import database
        
        # We need a real DB to test `_record_cost` DB operations
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        config.DB_PATH = db_path
        conn = sqlite3.connect(db_path)
        conn.executescript(database.SCHEMA_SQL)
        conn.commit()
        conn.close()
        
        # We also need to seed a session so `save_cost_data` works without failing FK/session lookup
        from app.db.queries import create_session
        sid = create_session("encounter", "Test", "id", None, "gemini", {}, None)
        
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(VALID_ANALYSIS_JSON))]
        mock_message.usage = MagicMock(input_tokens=100, output_tokens=50, cache_read_input_tokens=0)
        
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.return_value = mock_message
                run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, session_id=sid)
                
        # Check if cost was saved
        from app.db.queries import get_session
        row = get_session(sid)
        self.assertEqual(row["claude_input_tokens"], 100)
        self.assertEqual(row["claude_output_tokens"], 50)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_mock_cost_recording_exception(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        # Force an exception inside `_write_mock_cost_report` by patching save_cost_data
        with patch("app.db.queries.save_cost_data", side_effect=Exception("mock err")):
            # Should not raise
            MockAnalysisEngine._write_mock_cost_report(1, SAMPLE_TRANSCRIPT)

    def test_mock_analysis_with_session_id(self):
        from app.analysis.feedback_engine import MockAnalysisEngine
        import tempfile
        import sqlite3
        import config
        import os
        from app.db import database
        
        # Test mock analysis writing cost to DB
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        config.DB_PATH = db_path
        conn = sqlite3.connect(db_path)
        conn.executescript(database.SCHEMA_SQL)
        conn.commit()
        conn.close()
        
        from app.db.queries import create_session
        sid = create_session("encounter", "Test", "id", None, "gemini", {}, None)
        
        result = MockAnalysisEngine.run(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, session_id=sid)
        self.assertIn("summary_feedback", result)
        
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_missing_api_key_raises_value_error(self):
        from app.analysis.feedback_engine import run_analysis
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_invalid_json_response_raises_value_error(self):
        from app.analysis.feedback_engine import run_analysis
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="this is not json at all")]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.return_value = mock_message
                with self.assertRaises(ValueError):
                    run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)

    def test_api_exception_propagates(self):
        from app.analysis.feedback_engine import run_analysis
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.side_effect = ConnectionError("network error")
                with self.assertRaises(ConnectionError):
                    run_analysis(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL)


class TestComputeSelfDelta(unittest.TestCase):
    def test_basic_delta(self):
        from app.analysis.feedback_engine import _compute_self_delta
        delta = _compute_self_delta({"grammar": 7.5}, {"grammar": 5.0})
        self.assertEqual(delta, {"grammar": 2.5})

    def test_fluency_key_alias_both_directions(self):
        from app.analysis.feedback_engine import _compute_self_delta
        self.assertEqual(
            _compute_self_delta({"fluency": 6.0}, {"communication_fluency": 5.0}),
            {"fluency": 1.0},
        )
        self.assertEqual(
            _compute_self_delta({"communication_fluency": 6.0}, {"fluency": 5.0}),
            {"communication_fluency": 1.0},
        )

    def test_non_numeric_values_skipped(self):
        from app.analysis.feedback_engine import _compute_self_delta
        delta = _compute_self_delta(
            {"grammar": "bad", "professionalism": 8.0},
            {"grammar": 5.0, "professionalism": "also bad"},
        )
        self.assertEqual(delta, {})

    def test_missing_self_score_skipped(self):
        from app.analysis.feedback_engine import _compute_self_delta
        delta = _compute_self_delta({"grammar": 7.0, "medical_accuracy": 8.0},
                                    {"grammar": 6.0})
        self.assertEqual(delta, {"grammar": 1.0})

    def test_string_ai_score_coerced(self):
        from app.analysis.feedback_engine import _compute_self_delta
        delta = _compute_self_delta({"grammar": "7.5"}, {"grammar": 5.0})
        self.assertEqual(delta, {"grammar": 2.5})


if __name__ == "__main__":
    unittest.main()
