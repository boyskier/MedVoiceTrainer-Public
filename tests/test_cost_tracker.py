"""Tests for app/analysis/cost_tracker.py — token counting and cost computation."""
import json
import os
import shutil
import tempfile
import unittest


SAMPLE_SESSION = {
    "id": 42,
    "created_at": "2026-06-02T10:00:00",
    "mode": "encounter",
    "case_name": "Mr. Johnson",
    "voice_backend": "gemini",
    "duration_seconds": 300,
    "raw_transcript": json.dumps([
        {"turn_index": 0, "role": "patient", "text": "Hello, I have chest pain."},
        {"turn_index": 1, "role": "user", "text": "When did it start?"},
        {"turn_index": 2, "role": "patient", "text": "About two hours ago, doctor."},
    ]),
    "raw_case_json": json.dumps({"id": "cardio_001", "chief_complaint": "chest pain"}),
    "raw_eval_json": json.dumps({"name": "History Taking", "output_sections": ["scores", "summary"], "metrics": {}, "checklist": []}),
    "raw_claude_response": json.dumps({"overall_scores": {"grammar": 7.0}, "summary_feedback": "Good."}),
}


class TestCostComputations(unittest.TestCase):
    def test_claude_cost_zero_tokens_is_zero(self):
        from app.analysis.cost_tracker import compute_claude_cost
        self.assertEqual(compute_claude_cost(0, 0), 0.0)

    def test_claude_cost_input_only(self):
        from app.analysis.cost_tracker import compute_claude_cost, CLAUDE_INPUT_PRICE_PER_1M
        cost = compute_claude_cost(1_000_000, 0)
        self.assertAlmostEqual(cost, CLAUDE_INPUT_PRICE_PER_1M, places=4)

    def test_claude_cost_output_only(self):
        from app.analysis.cost_tracker import compute_claude_cost, CLAUDE_OUTPUT_PRICE_PER_1M
        cost = compute_claude_cost(0, 1_000_000)
        self.assertAlmostEqual(cost, CLAUDE_OUTPUT_PRICE_PER_1M, places=4)

    def test_claude_cached_tokens_billed_at_10_percent(self):
        from app.analysis.cost_tracker import compute_claude_cost, CLAUDE_INPUT_PRICE_PER_1M
        # 1M cached tokens should cost 10% of input price
        full_cost = compute_claude_cost(1_000_000, 0, cached_tokens=0)
        cached_cost = compute_claude_cost(1_000_000, 0, cached_tokens=1_000_000)
        ratio = cached_cost / full_cost
        self.assertAlmostEqual(ratio, 0.10, places=2)

    def test_claude_cost_returns_float(self):
        from app.analysis.cost_tracker import compute_claude_cost
        result = compute_claude_cost(5000, 1000)
        self.assertIsInstance(result, float)

    def test_claude_cost_nonnegative(self):
        from app.analysis.cost_tracker import compute_claude_cost
        self.assertGreaterEqual(compute_claude_cost(100, 100), 0.0)

    def test_gemini_cost_zero_duration_is_near_zero(self):
        from app.analysis.cost_tracker import compute_gemini_voice_cost
        cost = compute_gemini_voice_cost(0, 0)
        self.assertAlmostEqual(cost, 0.0, places=4)

    def test_gemini_cost_increases_with_duration(self):
        from app.analysis.cost_tracker import compute_gemini_voice_cost
        cost_60 = compute_gemini_voice_cost(60, 100)
        cost_300 = compute_gemini_voice_cost(300, 100)
        self.assertGreater(cost_300, cost_60)

    def test_openai_cost_zero_duration_near_zero(self):
        from app.analysis.cost_tracker import compute_openai_voice_cost
        cost = compute_openai_voice_cost(0, 0)
        # With 0 duration the audio token count is 0; output uses max(chars//4, 1)=1
        # so a tiny non-zero cost is expected. Just verify it's very small.
        self.assertLess(cost, 0.05)

    def test_openai_cost_more_expensive_than_gemini(self):
        """OpenAI audio pricing is significantly higher than Gemini."""
        from app.analysis.cost_tracker import compute_gemini_voice_cost, compute_openai_voice_cost
        gemini = compute_gemini_voice_cost(300, 1000)
        openai = compute_openai_voice_cost(300, 1000)
        self.assertGreater(openai, gemini)


class TestBuildReportFromSession(unittest.TestCase):
    def test_returns_session_cost_report(self):
        from app.analysis.cost_tracker import build_report_from_session, SessionCostReport
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertIsInstance(report, SessionCostReport)

    def test_session_id_copied(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertEqual(report.session_id, 42)

    def test_mode_copied(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertEqual(report.mode, "encounter")

    def test_duration_copied(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertEqual(report.duration_seconds, 300)

    def test_gemini_backend_computes_voice_cost(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertGreater(report.voice_cost_usd, 0.0)

    def test_openai_backend_computes_voice_cost(self):
        from app.analysis.cost_tracker import build_report_from_session
        session = dict(SAMPLE_SESSION, voice_backend="openai")
        report = build_report_from_session(session)
        self.assertGreater(report.voice_cost_usd, 0.0)

    def test_mock_backend_zero_voice_cost(self):
        from app.analysis.cost_tracker import build_report_from_session
        session = dict(SAMPLE_SESSION, voice_backend="mock")
        report = build_report_from_session(session)
        self.assertEqual(report.voice_cost_usd, 0.0)

    def test_total_cost_equals_sum(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        expected = round(report.claude_cost_usd + report.voice_cost_usd, 6)
        self.assertAlmostEqual(report.total_cost_usd, expected, places=6)

    def test_total_cost_nonnegative(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        self.assertGreaterEqual(report.total_cost_usd, 0.0)

    def test_transcript_chars_counted_from_ai_turns_only(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION)
        # AI turns: "Hello, I have chest pain." + "About two hours ago, doctor."
        expected_chars = len("Hello, I have chest pain.") + len("About two hours ago, doctor.")
        self.assertEqual(report.voice_transcript_chars, expected_chars)

    def test_with_real_claude_message_uses_exact_tokens(self):
        """When claude_response_obj is provided, use its usage attribute."""
        from app.analysis.cost_tracker import build_report_from_session
        from unittest.mock import MagicMock
        mock_msg = MagicMock()
        mock_msg.usage.input_tokens = 5000
        mock_msg.usage.output_tokens = 800
        mock_msg.usage.cache_read_input_tokens = 200
        report = build_report_from_session(SAMPLE_SESSION, claude_response_obj=mock_msg)
        self.assertEqual(report.claude_input_tokens, 5000)
        self.assertEqual(report.claude_output_tokens, 800)
        self.assertEqual(report.claude_cached_input_tokens, 200)

    def test_without_claude_response_uses_estimation(self):
        from app.analysis.cost_tracker import build_report_from_session
        report = build_report_from_session(SAMPLE_SESSION, claude_response_obj=None)
        # Estimated tokens should be positive
        self.assertGreaterEqual(report.claude_input_tokens, 0)
        # Notes should mention estimation
        self.assertTrue(any("estimated" in n.lower() for n in report.notes))

    def test_missing_raw_transcript_does_not_crash(self):
        from app.analysis.cost_tracker import build_report_from_session
        session = dict(SAMPLE_SESSION)
        del session["raw_transcript"]
        report = build_report_from_session(session)
        self.assertIsNotNone(report)

    def test_invalid_json_eval_case_handles_exception(self):
        from app.analysis.cost_tracker import build_report_from_session
        session = dict(SAMPLE_SESSION)
        session["raw_case_json"] = "{"
        report = build_report_from_session(session)
        self.assertEqual(report.claude_input_tokens, 0)

    def test_invalid_json_transcript_handles_exception(self):
        from app.analysis.cost_tracker import build_report_from_session
        session = dict(SAMPLE_SESSION)
        session["raw_transcript"] = "["
        report = build_report_from_session(session)
        self.assertEqual(report.voice_transcript_chars, 0)


class TestFormatReportText(unittest.TestCase):
    def _get_report(self):
        from app.analysis.cost_tracker import build_report_from_session
        return build_report_from_session(SAMPLE_SESSION)

    def test_returns_string(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIsInstance(text, str)

    def test_contains_session_id(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIn("42", text)

    def test_contains_total_cost_line(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIn("TOTAL COST", text)

    def test_contains_claude_section(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIn("Claude", text)

    def test_contains_gemini_section_for_gemini_backend(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIn("Gemini", text)

    def test_contains_openai_section_for_openai_backend(self):
        from app.analysis.cost_tracker import build_report_from_session, format_report_text
        session = dict(SAMPLE_SESSION, voice_backend="openai")
        report = build_report_from_session(session)
        text = format_report_text(report)
        self.assertIn("OpenAI", text)

    def test_contains_mode_and_case(self):
        from app.analysis.cost_tracker import format_report_text
        text = format_report_text(self._get_report())
        self.assertIn("encounter", text.lower())
        self.assertIn("Mr. Johnson", text)

    def test_notes_included_when_present(self):
        from app.analysis.cost_tracker import build_report_from_session, format_report_text
        report = build_report_from_session(SAMPLE_SESSION, claude_response_obj=None)
        text = format_report_text(report)
        self.assertIn("Notes:", text)


class TestSaveCostReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_report(self):
        from app.analysis.cost_tracker import build_report_from_session
        return build_report_from_session(SAMPLE_SESSION)

    def test_creates_txt_file(self):
        from app.analysis.cost_tracker import save_cost_report
        path = save_cost_report(self._make_report(), self.tmpdir)
        self.assertTrue(os.path.exists(path))

    def test_file_ends_with_txt(self):
        from app.analysis.cost_tracker import save_cost_report
        path = save_cost_report(self._make_report(), self.tmpdir)
        self.assertTrue(path.endswith(".txt"))

    def test_file_is_nonzero_size(self):
        from app.analysis.cost_tracker import save_cost_report
        path = save_cost_report(self._make_report(), self.tmpdir)
        self.assertGreater(os.path.getsize(path), 100)

    def test_file_contains_total_cost(self):
        from app.analysis.cost_tracker import save_cost_report
        path = save_cost_report(self._make_report(), self.tmpdir)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("TOTAL COST", content)

    def test_creates_output_dir_if_missing(self):
        from app.analysis.cost_tracker import save_cost_report
        new_dir = os.path.join(self.tmpdir, "nested", "reports")
        path = save_cost_report(self._make_report(), new_dir)
        self.assertTrue(os.path.exists(path))

    def test_returns_path_string(self):
        from app.analysis.cost_tracker import save_cost_report
        result = save_cost_report(self._make_report(), self.tmpdir)
        self.assertIsInstance(result, str)
        self.assertTrue(os.path.isabs(result))


if __name__ == "__main__":
    unittest.main()
