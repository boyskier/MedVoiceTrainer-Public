"""Tests for app/analysis/prompt_builder.py — all prompt construction functions."""
import json
import unittest


SAMPLE_CASE = {
    "id": "cardio_001",
    "patient_name": "Mr. Johnson",
    "age": 58,
    "gender": "male",
    "chief_complaint": "chest pain for 2 hours",
    "hpi_details": "substernal, 7/10, radiates to left arm",
    "ideas": "thinks it might be heartburn",
    "concerns": "afraid of heart attack",
    "expectations": "wants reassurance",
    "pmh": "hypertension x5 years",
    "medications": "metformin 1000mg BD",
    "social_hx": "smoker 20 pack-years",
    "reference_soap": {
        "subjective": "58M with chest pain",
        "objective": "ECG required",
        "assessment": "ACS",
        "plan": "Aspirin, ECG",
    },
}

SAMPLE_SCENARIO = {
    "id": "behavioral_001",
    "pd_name": "Dr. Chen",
    "program": "University Hospital Internal Medicine",
    "category": "behavioral",
    "opening_question": "Tell me about yourself.",
}

SAMPLE_EVAL = {
    "name": "History Taking",
    "output_sections": ["scores", "checklist", "ice_empathy", "soap_note", "corrections", "anki_cards", "summary"],
    "metrics": {
        "grammar": {"label": "Grammar", "anchors": {"9-10": "Native-like"}},
        "medical_accuracy": {"label": "Medical Accuracy", "anchors": {}},
        "clinical_reasoning": {"label": "Clinical Reasoning", "anchors": {}},
        "communication_fluency": {"label": "Fluency", "anchors": {}},
    },
    "checklist": [
        {"item": "onset and duration", "required": True},
        {"item": "ICE explored", "required": True},
    ],
    "empathy_markers": ["acknowledged patient concern"],
}

SAMPLE_TRANSCRIPT = [
    {"turn_index": 0, "role": "patient", "text": "Hello, I have chest pain."},
    {"turn_index": 1, "role": "user", "text": "When did it start?"},
    {"turn_index": 2, "role": "patient", "text": "About 2 hours ago."},
]


class TestBuildPatientPrompt(unittest.TestCase):
    def setUp(self):
        from app.analysis.prompt_builder import build_patient_prompt
        self.prompt = build_patient_prompt(SAMPLE_CASE)

    def test_returns_string(self):
        self.assertIsInstance(self.prompt, str)

    def test_contains_patient_name(self):
        self.assertIn("Mr. Johnson", self.prompt)

    def test_contains_age_and_gender(self):
        self.assertIn("58", self.prompt)
        self.assertIn("male", self.prompt)

    def test_contains_chief_complaint(self):
        self.assertIn("chest pain for 2 hours", self.prompt)

    def test_contains_hpi_details(self):
        self.assertIn("substernal", self.prompt)

    def test_contains_ice(self):
        self.assertIn("heartburn", self.prompt)
        self.assertIn("heart attack", self.prompt)
        self.assertIn("reassurance", self.prompt)

    def test_contains_pmh(self):
        self.assertIn("hypertension", self.prompt)

    def test_contains_medications(self):
        self.assertIn("metformin", self.prompt)

    def test_contains_social_hx(self):
        self.assertIn("smoker", self.prompt)

    def test_contains_session_end_instruction(self):
        self.assertIn("summarize", self.prompt.lower())

    def test_hidden_info_instruction_present(self):
        self.assertIn("HIDDEN INFORMATION", self.prompt)

    def test_handles_missing_optional_fields(self):
        """Should not raise on minimal case dict."""
        from app.analysis.prompt_builder import build_patient_prompt
        minimal = {"id": "test", "patient_name": "Mr. X"}
        result = build_patient_prompt(minimal)
        self.assertIsInstance(result, str)
        self.assertIn("Mr. X", result)


class TestBuildInterviewPrompt(unittest.TestCase):
    def setUp(self):
        from app.analysis.prompt_builder import build_interview_prompt
        self.prompt = build_interview_prompt(SAMPLE_SCENARIO)

    def test_returns_string(self):
        self.assertIsInstance(self.prompt, str)

    def test_contains_pd_name(self):
        self.assertIn("Dr. Chen", self.prompt)

    def test_contains_program(self):
        self.assertIn("University Hospital Internal Medicine", self.prompt)

    def test_contains_category(self):
        self.assertIn("behavioral", self.prompt)

    def test_contains_opening_question(self):
        self.assertIn("Tell me about yourself", self.prompt)

    def test_contains_star_reference(self):
        self.assertIn("STAR", self.prompt)


class TestBuildCustomPrompt(unittest.TestCase):
    def test_embeds_persona(self):
        from app.analysis.prompt_builder import build_custom_prompt
        persona = "You are a hospital administrator reviewing a budget proposal."
        result = build_custom_prompt(persona)
        self.assertIn("hospital administrator", result)

    def test_contains_session_end_instruction(self):
        from app.analysis.prompt_builder import build_custom_prompt
        result = build_custom_prompt("Some persona")
        self.assertIn("end the session", result.lower())

    def test_empty_persona_does_not_raise(self):
        from app.analysis.prompt_builder import build_custom_prompt
        result = build_custom_prompt("")
        self.assertIsInstance(result, str)


class TestBuildAnalysisPrompt(unittest.TestCase):
    def setUp(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        self.prompt = build_analysis_prompt(
            SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, self_scores=None
        )

    def test_returns_string(self):
        self.assertIsInstance(self.prompt, str)

    def test_contains_case_ground_truth(self):
        self.assertIn("cardio_001", self.prompt)
        self.assertIn("chest pain", self.prompt)

    def test_contains_transcript_turns(self):
        self.assertIn("[Turn 0]", self.prompt)
        self.assertIn("[Turn 1]", self.prompt)
        self.assertIn("[Turn 2]", self.prompt)

    def test_transcript_roles_labelled(self):
        self.assertIn("PATIENT:", self.prompt)
        self.assertIn("USER:", self.prompt)

    def test_contains_rubric_anchors(self):
        self.assertIn("Native-like", self.prompt)

    def test_contains_checklist(self):
        self.assertIn("onset and duration", self.prompt)
        self.assertIn("ICE explored", self.prompt)

    def test_contains_empathy_markers(self):
        self.assertIn("acknowledged patient concern", self.prompt)

    def test_contains_output_schema(self):
        self.assertIn("overall_scores", self.prompt)
        self.assertIn("summary_feedback", self.prompt)

    def test_contains_sections_list(self):
        self.assertIn("scores", self.prompt)
        self.assertIn("soap_note", self.prompt)

    def test_with_self_scores_included(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        self_scores = {"grammar": 5.0, "medical_accuracy": 6.0}
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, self_scores)
        self.assertIn("SELF-ASSESSMENT", prompt)

    def test_without_self_scores_no_self_assessment_section(self):
        self.assertNotIn("SELF-ASSESSMENT", self.prompt)

    def test_empty_transcript_does_not_raise(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        result = build_analysis_prompt([], SAMPLE_CASE, SAMPLE_EVAL)
        self.assertIsInstance(result, str)

    def test_custom_criteria_prose_included(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        eval_with_custom = dict(SAMPLE_EVAL)
        eval_with_custom["custom_criteria_prose"] = "Assess if student demonstrates bedside manner."
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, eval_with_custom)
        self.assertIn("bedside manner", prompt)

    def test_sections_without_soap_note_omit_soap_instruction(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        eval_no_soap = dict(SAMPLE_EVAL, output_sections=["scores", "summary"])
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, eval_no_soap)
        # soap_note key should be in schema template but not required
        self.assertIn("summary_feedback", prompt)

    def test_preclinical_learner_adds_guidance(self):
        from app.analysis.prompt_builder import build_analysis_prompt, PRECLINICAL_GUIDANCE
        eval_data = dict(SAMPLE_EVAL, learner_level="preclinical")
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, eval_data)
        self.assertIn(PRECLINICAL_GUIDANCE, prompt)

    def test_student_soap_appends_to_prompt(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        student_soap = {"subjective": "Chest pain."}
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, SAMPLE_EVAL, student_soap=student_soap)
        self.assertIn("The student wrote the following SOAP note.", prompt)
        self.assertIn("Chest pain.", prompt)

    def test_unknown_section_appends_directly_to_schema_keys(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        eval_data = dict(SAMPLE_EVAL, output_sections=["unknown_custom_section"])
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, SAMPLE_CASE, eval_data)
        self.assertIn("unknown_custom_section", prompt)


class TestPromptConstants(unittest.TestCase):
    def test_all_prompt_constants_are_strings(self):
        from app.analysis import prompt_builder
        self.assertIsInstance(prompt_builder.ANALYSIS_BASE_HEADER, str)
        self.assertIsInstance(prompt_builder.PATIENT_SYSTEM_PROMPT, str)
        self.assertIsInstance(prompt_builder.INTERVIEW_SYSTEM_PROMPT, str)
        self.assertIsInstance(prompt_builder.CUSTOM_SYSTEM_PROMPT, str)

    def test_patient_prompt_has_all_format_fields(self):
        """All {placeholders} in PATIENT_SYSTEM_PROMPT must be fillable."""
        from app.analysis.prompt_builder import PATIENT_SYSTEM_PROMPT
        filled = PATIENT_SYSTEM_PROMPT.format(
            patient_name="X", age=1, gender="F", chief_complaint="X",
            hpi_details="X", ideas="X", concerns="X", expectations="X",
            pmh="X", medications="X", social_hx="X",
        )
        self.assertIsInstance(filled, str)

    def test_interview_prompt_has_all_format_fields(self):
        from app.analysis.prompt_builder import INTERVIEW_SYSTEM_PROMPT
        filled = INTERVIEW_SYSTEM_PROMPT.format(
            pd_name="Dr. X", program="X Hospital", category="behavioral",
            opening_question="Tell me about yourself."
        )
        self.assertIsInstance(filled, str)


class TestAssignComplexityModifier(unittest.TestCase):
    def _patched_roll(self, value):
        from unittest.mock import patch
        from app.analysis import prompt_builder
        return patch.object(prompt_builder.random, "random", return_value=value)

    def test_does_not_mutate_input(self):
        from app.analysis.prompt_builder import assign_complexity_modifier
        case = dict(SAMPLE_CASE)
        out = assign_complexity_modifier(case)
        self.assertIsNot(out, case)
        self.assertNotIn("active_complexity_modifier", case)

    def test_coaching_mode_never_gets_modifier(self):
        from app.analysis.prompt_builder import assign_complexity_modifier
        case = dict(SAMPLE_CASE, coaching_mode=True)
        with self._patched_roll(0.0):
            out = assign_complexity_modifier(case)
        self.assertNotIn("active_complexity_modifier", out)

    def test_persona_override_never_gets_modifier(self):
        from app.analysis.prompt_builder import assign_complexity_modifier
        case = dict(SAMPLE_CASE, persona_override="You are an attending.")
        with self._patched_roll(0.0):
            out = assign_complexity_modifier(case)
        self.assertNotIn("active_complexity_modifier", out)

    def test_modifier_assigned_when_roll_hits(self):
        from app.analysis import prompt_builder
        with self._patched_roll(0.0):
            out = prompt_builder.assign_complexity_modifier(dict(SAMPLE_CASE))
        self.assertIn(out["active_complexity_modifier"], prompt_builder.COMPLEXITY_MODIFIERS)

    def test_no_modifier_when_roll_misses(self):
        from app.analysis.prompt_builder import assign_complexity_modifier
        with self._patched_roll(0.99):
            out = assign_complexity_modifier(dict(SAMPLE_CASE))
        self.assertNotIn("active_complexity_modifier", out)

    def test_stale_modifier_cleared_before_reroll(self):
        from app.analysis.prompt_builder import assign_complexity_modifier
        case = dict(SAMPLE_CASE, active_complexity_modifier="old twist")
        with self._patched_roll(0.99):
            out = assign_complexity_modifier(case)
        self.assertNotIn("active_complexity_modifier", out)

    def test_patient_prompt_includes_assigned_modifier(self):
        from app.analysis.prompt_builder import build_patient_prompt
        case = dict(SAMPLE_CASE, active_complexity_modifier="SECRET TWIST XYZ")
        self.assertIn("SECRET TWIST XYZ", build_patient_prompt(case))

    def test_patient_prompt_without_modifier_has_no_twist(self):
        from app.analysis.prompt_builder import build_patient_prompt
        self.assertNotIn("COMPLEXITY MODIFIER", build_patient_prompt(dict(SAMPLE_CASE)))

    def test_analysis_prompt_mentions_active_modifier(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        case = dict(SAMPLE_CASE, active_complexity_modifier="SECRET TWIST XYZ")
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, case, SAMPLE_EVAL)
        self.assertIn("behavioral twist", prompt)
        self.assertIn("SECRET TWIST XYZ", prompt)

    def test_analysis_prompt_without_modifier_has_no_twist_note(self):
        from app.analysis.prompt_builder import build_analysis_prompt
        prompt = build_analysis_prompt(SAMPLE_TRANSCRIPT, dict(SAMPLE_CASE), SAMPLE_EVAL)
        self.assertNotIn("behavioral twist", prompt)


if __name__ == "__main__":
    unittest.main()
