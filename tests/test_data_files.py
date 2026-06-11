"""Tests for seed data JSON files — structure validation."""
import json
import os
import unittest

import config


REQUIRED_CASE_FIELDS = [
    "id", "system", "difficulty", "eval_template",
    "patient_name", "age", "gender", "chief_complaint",
    "hpi_details", "ideas", "concerns", "expectations",
    "pmh", "medications", "social_hx",
]

# Skill drills (e.g. empathy/plain-language/numbers) supply a free-form
# `persona_override` instead of a patient history, so they are exempt from the
# history-taking field requirements.
REQUIRED_DRILL_FIELDS = [
    "id", "system", "difficulty", "eval_template", "patient_name",
    "chief_complaint", "persona_override",
]


def is_drill(case: dict) -> bool:
    return bool(case.get("persona_override"))

REQUIRED_EVAL_FIELDS = ["name", "output_sections", "metrics", "checklist"]

VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
VALID_OUTPUT_SECTIONS = {
    "scores", "checklist", "history_completeness", "ice_empathy",
    "soap_note", "corrections", "anki_cards", "summary",
}
VALID_METRIC_KEYS = {"grammar", "medical_accuracy", "clinical_reasoning", "communication_fluency", "professionalism"}


def load_all_cases() -> list[dict]:
    cases = []
    for system in config.CASE_SYSTEMS:
        system_dir = os.path.join(config.CASES_DIR, system)
        if not os.path.isdir(system_dir):
            continue
        for fname in os.listdir(system_dir):
            if fname.endswith(".json"):
                with open(os.path.join(system_dir, fname), encoding="utf-8") as f:
                    cases.append(json.load(f))
    return cases


def load_all_eval_templates() -> list[dict]:
    templates = []
    if not os.path.isdir(config.EVAL_DIR):
        return templates
    for fname in os.listdir(config.EVAL_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(config.EVAL_DIR, fname), encoding="utf-8") as f:
                templates.append(json.load(f))
    return templates


def load_interview_scenarios() -> list[dict]:
    scenarios = []
    if not os.path.isdir(config.INTERVIEW_BANKS_DIR):
        return scenarios
    for fname in os.listdir(config.INTERVIEW_BANKS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(config.INTERVIEW_BANKS_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            scenarios.extend(data.get("scenarios", []))
    return scenarios


class TestCaseFiles(unittest.TestCase):
    def setUp(self):
        self.cases = load_all_cases()

    def test_minimum_case_count(self):
        self.assertGreaterEqual(len(self.cases), 8, "Need at least 8 cases (2 per system)")

    def test_all_systems_have_cases(self):
        systems_present = {c["system"] for c in self.cases}
        for system in ["cardiology", "gastroenterology", "pulmonology", "neurology"]:
            self.assertIn(system, systems_present, f"No cases for system: {system}")

    def test_each_system_has_at_least_two_cases(self):
        from collections import Counter
        counts = Counter(c["system"] for c in self.cases)
        for system, count in counts.items():
            self.assertGreaterEqual(count, 2, f"System {system} has only {count} case(s)")

    def test_required_fields_present(self):
        for case in self.cases:
            required = REQUIRED_DRILL_FIELDS if is_drill(case) else REQUIRED_CASE_FIELDS
            for field in required:
                self.assertIn(field, case, f"Case {case.get('id', '?')} missing field: {field}")

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate case IDs found")

    def test_ids_are_nonempty_strings(self):
        for case in self.cases:
            self.assertIsInstance(case["id"], str)
            self.assertTrue(len(case["id"]) > 0)

    def test_age_is_positive_integer(self):
        for case in self.cases:
            if is_drill(case):
                continue
            self.assertIsInstance(case["age"], int, f"Case {case['id']}: age must be int")
            self.assertGreater(case["age"], 0)

    def test_difficulty_is_valid(self):
        for case in self.cases:
            self.assertIn(case["difficulty"], VALID_DIFFICULTIES,
                          f"Case {case['id']}: invalid difficulty '{case['difficulty']}'")

    def test_gender_is_valid(self):
        for case in self.cases:
            if is_drill(case):
                continue
            self.assertIn(case["gender"].lower(), {"male", "female", "other"},
                          f"Case {case['id']}: invalid gender '{case['gender']}'")

    def test_reference_soap_structure(self):
        for case in self.cases:
            if "reference_soap" in case:
                soap = case["reference_soap"]
                self.assertIsInstance(soap, dict)
                for key in ("subjective", "objective", "assessment", "plan"):
                    self.assertIn(key, soap, f"Case {case['id']}: reference_soap missing key '{key}'")

    def test_eval_template_references_existing_file(self):
        for case in self.cases:
            tpl = case.get("eval_template", "")
            if tpl:
                path = os.path.join(config.EVAL_DIR, f"{tpl}.json")
                self.assertTrue(os.path.exists(path),
                                f"Case {case['id']}: eval_template '{tpl}' not found at {path}")

    def test_chief_complaint_is_nonempty_string(self):
        for case in self.cases:
            self.assertIsInstance(case["chief_complaint"], str)
            self.assertGreater(len(case["chief_complaint"]), 5)

    def test_learning_objectives_if_present(self):
        for case in self.cases:
            if "learning_objectives" in case:
                obj = case["learning_objectives"]
                self.assertIsInstance(obj, list)
                for item in obj:
                    self.assertIsInstance(item, str)


class TestEvalTemplates(unittest.TestCase):
    def setUp(self):
        self.templates = load_all_eval_templates()

    def test_minimum_template_count(self):
        self.assertGreaterEqual(len(self.templates), 5, "Need at least 5 eval templates")

    def test_required_fields_present(self):
        for tpl in self.templates:
            for field in REQUIRED_EVAL_FIELDS:
                self.assertIn(field, tpl, f"Template {tpl.get('name', '?')} missing field: {field}")

    def test_names_are_nonempty_strings(self):
        for tpl in self.templates:
            self.assertIsInstance(tpl["name"], str)
            self.assertGreater(len(tpl["name"]), 0)

    def test_output_sections_are_valid(self):
        for tpl in self.templates:
            for section in tpl.get("output_sections", []):
                self.assertIn(section, VALID_OUTPUT_SECTIONS,
                              f"Template {tpl['name']}: unknown section '{section}'")

    def test_output_sections_always_includes_summary(self):
        for tpl in self.templates:
            self.assertIn("summary", tpl.get("output_sections", []),
                          f"Template {tpl['name']}: must include 'summary' section")

    def test_metrics_are_dicts(self):
        for tpl in self.templates:
            self.assertIsInstance(tpl["metrics"], dict)
            self.assertGreater(len(tpl["metrics"]), 0)

    def test_each_metric_has_label(self):
        for tpl in self.templates:
            for key, metric in tpl["metrics"].items():
                self.assertIn("label", metric,
                              f"Template {tpl['name']}: metric '{key}' missing 'label'")

    def test_checklist_items_have_required_field(self):
        for tpl in self.templates:
            for item in tpl.get("checklist", []):
                self.assertIn("item", item)
                self.assertIn("required", item)
                self.assertIsInstance(item["required"], bool)

    def test_empathy_markers_is_list(self):
        for tpl in self.templates:
            self.assertIsInstance(tpl.get("empathy_markers", []), list)

    def test_names_are_unique(self):
        names = [t["name"] for t in self.templates]
        self.assertEqual(len(names), len(set(names)), "Duplicate template names")


class TestInterviewBanks(unittest.TestCase):
    def setUp(self):
        self.scenarios = load_interview_scenarios()

    def test_minimum_scenario_count(self):
        self.assertGreaterEqual(len(self.scenarios), 11,
                                "Need at least 11 interview scenarios (5 behavioral + 3 clinical + 3 IMG)")

    def test_behavioral_category_has_five(self):
        behavioral = [s for s in self.scenarios if s.get("category") == "behavioral"]
        self.assertGreaterEqual(len(behavioral), 5)

    def test_clinical_category_has_three(self):
        clinical = [s for s in self.scenarios if s.get("category") == "clinical"]
        self.assertGreaterEqual(len(clinical), 3)

    def test_img_specific_category_has_three(self):
        img = [s for s in self.scenarios if s.get("category") == "img_specific"]
        self.assertGreaterEqual(len(img), 3)

    def test_required_fields(self):
        for s in self.scenarios:
            for field in ("id", "eval_template", "pd_name", "program", "category", "opening_question"):
                self.assertIn(field, s, f"Scenario {s.get('id', '?')} missing: {field}")

    def test_ids_are_unique(self):
        ids = [s["id"] for s in self.scenarios]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate scenario IDs")

    def test_follow_up_pool_is_list(self):
        for s in self.scenarios:
            pool = s.get("follow_up_pool", [])
            self.assertIsInstance(pool, list)
            for item in pool:
                self.assertIsInstance(item, str)

    def test_img_specific_flag_is_bool(self):
        for s in self.scenarios:
            self.assertIsInstance(s.get("img_specific", False), bool)


if __name__ == "__main__":
    unittest.main()
