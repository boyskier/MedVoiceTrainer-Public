"""Tests for the personalised 'Practice My Mistakes' review builder."""
import json
import unittest

from app.analysis import review_builder
from app.analysis.prompt_builder import build_patient_prompt


def _session(corrections):
    return {"corrections": json.dumps(corrections)}


class TestAggregateCorrections(unittest.TestCase):
    def test_empty_history_returns_empty(self):
        self.assertEqual(review_builder.aggregate_corrections([]), [])

    def test_handles_missing_or_bad_corrections(self):
        sessions = [
            {"corrections": None},
            {"corrections": "not json"},
            {"corrections": json.dumps("a string, not a list")},
            {},  # no key at all
        ]
        self.assertEqual(review_builder.aggregate_corrections(sessions), [])

    def test_dedupes_and_counts_by_corrected_phrase(self):
        sessions = [
            _session([{"original": "since when", "corrected": "How long have you had it?"}]),
            _session([{"original": "since when?", "corrected": "how long have you had it?  "}]),
        ]
        result = review_builder.aggregate_corrections(sessions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["count"], 2)

    def test_ranks_by_frequency(self):
        sessions = [
            _session([
                {"original": "a", "corrected": "rare phrase"},
                {"original": "b", "corrected": "common phrase"},
            ]),
            _session([{"original": "c", "corrected": "common phrase"}]),
            _session([{"original": "d", "corrected": "common phrase"}]),
        ]
        result = review_builder.aggregate_corrections(sessions)
        self.assertEqual(result[0]["corrected"], "common phrase")
        self.assertEqual(result[0]["count"], 3)

    def test_respects_max_items(self):
        corrections = [{"original": f"o{i}", "corrected": f"phrase {i}"} for i in range(20)]
        result = review_builder.aggregate_corrections([_session(corrections)], max_items=6)
        self.assertEqual(len(result), 6)

    def test_skips_blank_corrected(self):
        sessions = [_session([{"original": "x", "corrected": "   "}, {"original": "y"}])]
        self.assertEqual(review_builder.aggregate_corrections(sessions), [])

    def test_skips_non_dict_corrections(self):
        sessions = [_session(["not a dict", {"original": "x", "corrected": "y"}])]
        result = review_builder.aggregate_corrections(sessions)
        self.assertEqual(len(result), 1)

    def test_prepare_targets_calls_db(self):
        from unittest.mock import patch
        from app.analysis import review_builder
        with patch("app.db.queries.list_sessions", return_value=[_session([{"original": "x", "corrected": "y"}])]):
            result = review_builder.prepare_targets()
            self.assertEqual(len(result), 1)


class TestBuildReviewArtifacts(unittest.TestCase):
    def setUp(self):
        self.targets = [
            {"original": "Can you tell me about the pain?",
             "corrected": "Could you describe the pain for me?",
             "explanation": "open phrasing invites richer description", "count": 3},
            {"original": "since when the fever",
             "corrected": "How long have you had the fever?",
             "explanation": "", "count": 1},
        ]

    def test_case_has_persona_override_with_targets(self):
        case = review_builder.build_review_case(self.targets)
        self.assertTrue(case.get("coaching_mode"))
        self.assertEqual(case["eval_template"], "correction_review")
        persona = case["persona_override"]
        self.assertIn("Could you describe the pain for me?", persona)
        self.assertIn("How long have you had the fever?", persona)
        # The coach must not be told to reveal the answer.
        self.assertIn("without telling them the answer", persona)

    def test_phrase_helper_lists_target_phrases(self):
        case = review_builder.build_review_case(self.targets)
        cats = case["phrase_categories"]
        phrases = cats[0]["phrases"]
        self.assertIn("Could you describe the pain for me?", phrases)

    def test_patient_prompt_uses_override_and_coaching(self):
        case = review_builder.build_review_case(self.targets)
        prompt = build_patient_prompt(case)
        self.assertIn("PERSONALISED REVIEW", prompt)
        self.assertIn("COACHING MODE", prompt)  # coaching addendum appended

    def test_eval_injects_one_checklist_item_per_target(self):
        ev = review_builder.build_review_eval(self.targets)
        self.assertEqual(len(ev["checklist"]), len(self.targets))
        for item in ev["checklist"]:
            self.assertIn("item", item)
            self.assertTrue(item["required"])
        self.assertIn("summary", ev["output_sections"])


if __name__ == "__main__":
    unittest.main()
