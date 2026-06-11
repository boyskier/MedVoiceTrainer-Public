"""Tests for app/analysis/analysis_providers.py and feedback-backend routing."""
import json
import unittest
from unittest.mock import MagicMock, patch

SAMPLE_PROMPT = "Analyse this transcript and return JSON."
VALID_JSON = {"overall_scores": {"grammar": 7.0}, "summary_feedback": "Nice job overall."}


class TestCallAnalysisClaude(unittest.TestCase):
    def test_claude_returns_text_and_usage(self):
        from app.analysis.analysis_providers import call_analysis
        msg = MagicMock()
        msg.content = [MagicMock(text=json.dumps(VALID_JSON))]
        msg.usage = MagicMock(input_tokens=120, output_tokens=60, cache_read_input_tokens=10)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}):
            with patch("anthropic.Anthropic") as Client:
                Client.return_value.messages.create.return_value = msg
                text, usage = call_analysis("claude", SAMPLE_PROMPT)
        self.assertIn("overall_scores", text)
        self.assertEqual(usage, {"input_tokens": 120, "output_tokens": 60, "cached_tokens": 10})

    def test_claude_missing_key_raises(self):
        from app.analysis.analysis_providers import call_analysis
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                call_analysis("claude", SAMPLE_PROMPT)
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))


class TestCallAnalysisGemini(unittest.TestCase):
    def test_gemini_returns_text_and_usage(self):
        from app.analysis.analysis_providers import call_analysis
        resp = MagicMock()
        resp.text = json.dumps(VALID_JSON)
        resp.usage_metadata = MagicMock(
            prompt_token_count=200, candidates_token_count=90, cached_content_token_count=0
        )
        fake_genai = MagicMock()
        fake_genai.Client.return_value.models.generate_content.return_value = resp
        fake_google = MagicMock()
        fake_google.genai = fake_genai  # `from google import genai`
        modules = {
            "google": fake_google,
            "google.genai": fake_genai,
            "google.genai.types": fake_genai.types,
        }
        with patch.dict("os.environ", {"GEMINI_API_KEY": "k"}):
            with patch.dict("sys.modules", modules):
                text, usage = call_analysis("gemini", SAMPLE_PROMPT)
        self.assertIn("overall_scores", text)
        self.assertEqual(usage["input_tokens"], 200)
        self.assertEqual(usage["output_tokens"], 90)

    def test_gemini_missing_key_raises(self):
        from app.analysis.analysis_providers import call_analysis
        modules = {
            "google": MagicMock(),
            "google.genai": MagicMock(),
            "google.genai.types": MagicMock(),
        }
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict("sys.modules", modules):
                with self.assertRaises(ValueError) as ctx:
                    call_analysis("gemini", SAMPLE_PROMPT)
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


class TestCallAnalysisOpenAI(unittest.TestCase):
    def test_openai_returns_text_and_usage(self):
        from app.analysis.analysis_providers import call_analysis
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=json.dumps(VALID_JSON)))]
        resp.usage = MagicMock(prompt_tokens=150, completion_tokens=70)
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = resp
        with patch.dict("os.environ", {"OPENAI_API_KEY": "k"}):
            with patch.dict("sys.modules", {"openai": fake_openai}):
                text, usage = call_analysis("openai", SAMPLE_PROMPT)
        self.assertIn("overall_scores", text)
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 70)
        self.assertEqual(usage["cached_tokens"], 0)
        # GPT-5.x reasoning models reject max_tokens/temperature — verify the
        # call uses the reasoning-model parameter names instead.
        kwargs = fake_openai.OpenAI.return_value.chat.completions.create.call_args.kwargs
        self.assertIn("max_completion_tokens", kwargs)
        self.assertNotIn("max_tokens", kwargs)
        self.assertNotIn("temperature", kwargs)

    def test_openai_missing_key_raises(self):
        from app.analysis.analysis_providers import call_analysis
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=True):
            with patch.dict("sys.modules", {"openai": MagicMock()}):
                with self.assertRaises(ValueError) as ctx:
                    call_analysis("openai", SAMPLE_PROMPT)
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))


class TestRunAnalysisRouting(unittest.TestCase):
    """run_analysis() should honour the feedback_backend setting."""

    SAMPLE_TRANSCRIPT = [{"turn_index": 0, "role": "patient", "text": "I have a cough."}]
    SAMPLE_CASE = {"id": "pulm_001", "chief_complaint": "cough"}
    SAMPLE_EVAL = {"output_sections": ["scores", "summary"]}

    def test_routes_to_gemini_when_selected(self):
        from app.analysis.feedback_engine import run_analysis
        with patch("app.analysis.feedback_engine._resolve_feedback_backend", return_value="gemini"):
            with patch("app.analysis.analysis_providers.call_analysis",
                       return_value=(json.dumps(VALID_JSON), {"input_tokens": 1, "output_tokens": 1, "cached_tokens": 0})) as call:
                result = run_analysis(self.SAMPLE_TRANSCRIPT, self.SAMPLE_CASE, self.SAMPLE_EVAL)
        call.assert_called_once()
        self.assertEqual(call.call_args[0][0], "gemini")
        self.assertEqual(result["summary_feedback"], "Nice job overall.")

    def test_invalid_json_raises_value_error_with_backend_name(self):
        from app.analysis.feedback_engine import run_analysis
        with patch("app.analysis.feedback_engine._resolve_feedback_backend", return_value="openai"):
            with patch("app.analysis.analysis_providers.call_analysis",
                       return_value=("not json", {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0})):
                with self.assertRaises(ValueError) as ctx:
                    run_analysis(self.SAMPLE_TRANSCRIPT, self.SAMPLE_CASE, self.SAMPLE_EVAL)
        self.assertIn("openai", str(ctx.exception))

    def test_resolve_backend_defaults_to_claude(self):
        from app.analysis.feedback_engine import _resolve_feedback_backend
        with patch("app.db.queries.get_setting", side_effect=Exception("no db")):
            self.assertEqual(_resolve_feedback_backend(), "claude")

    def test_resolve_backend_rejects_unknown(self):
        from app.analysis.feedback_engine import _resolve_feedback_backend
        with patch("app.db.queries.get_setting", return_value="llama"):
            self.assertEqual(_resolve_feedback_backend(), "claude")


class TestComputeAnalysisCost(unittest.TestCase):
    def test_gemini_and_openai_costs_positive(self):
        from app.analysis.cost_tracker import compute_analysis_cost
        self.assertGreater(compute_analysis_cost("gemini", 1_000_000, 1_000_000), 0.0)
        self.assertGreater(compute_analysis_cost("openai", 1_000_000, 1_000_000), 0.0)

    def test_claude_path_matches_compute_claude_cost(self):
        from app.analysis.cost_tracker import compute_analysis_cost, compute_claude_cost
        self.assertEqual(compute_analysis_cost("claude", 5000, 1000), compute_claude_cost(5000, 1000))

    def test_report_uses_provider_label_and_model(self):
        from app.analysis.cost_tracker import build_report_from_session, format_report_text
        session = {"id": 1, "voice_backend": "gemini", "mode": "encounter", "case_name": "x"}
        report = build_report_from_session(
            session, analysis_provider="openai",
            analysis_usage={"input_tokens": 100, "output_tokens": 50, "cached_tokens": 0},
        )
        self.assertEqual(report.analysis_provider, "openai")
        self.assertEqual(report.claude_input_tokens, 100)
        text = format_report_text(report)
        self.assertIn("OpenAI API", text)
        self.assertIn("gpt-5.1", text)


if __name__ == "__main__":
    unittest.main()
