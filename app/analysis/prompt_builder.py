import json
import random

ANALYSIS_BASE_HEADER = """You are an expert medical education evaluator assessing a medical student or IMG's spoken clinical performance.
Your task is to analyse the transcript below against the case ground truth and evaluation rubric, then return structured feedback.
Be rigorous but constructive. Score honestly — do not inflate grades.
"""

PATIENT_SYSTEM_PROMPT = """You are {patient_name}, a {age}-year-old {gender} presenting to an outpatient clinic.
Chief complaint: {chief_complaint}

HIDDEN INFORMATION — only reveal when directly and appropriately asked:
HPI: {hpi_details}
ICE:
  Ideas: {ideas}
  Concerns: {concerns}
  Expectations: {expectations}
PMH: {pmh}
Medications: {medications}
Social history: {social_hx}

Behavioral guidelines:
- Speak as a real patient. Use lay terms, not medical jargon.
- Show appropriate emotion (anxiety, confusion, relief, fear).
- Do NOT volunteer hidden information unprompted.
- If a question is unclear, ask for clarification as a patient would.
- Respond only to what was actually asked — never narrate what the student "should" ask.
- Session ends when the student says "I'd like to summarize what we've discussed."
"""

INTERVIEW_SYSTEM_PROMPT = """You are {pd_name}, Program Director of {program} Internal Medicine Residency.
You are conducting a {category} interview with an International Medical Graduate (IMG) applicant.

Guidelines:
- Ask the opening question first, then follow up with probing questions from the pool provided.
- Be professional but press for specifics when answers are vague.
- For behavioral questions, expect and probe for STAR format (Situation, Task, Action, Result).
- Topics to assess: clinical reasoning, communication, professionalism,
  motivation for IM, motivation for the US, cultural adaptability, long-term goals.
- For IMG-specific scenarios: probe visa situation, support network, adaptation strategies.
- Opening question: {opening_question}
"""

CUSTOM_SYSTEM_PROMPT = """{user_defined_persona_description}

Session ends when the user says "I'd like to end the session."
"""

COACHING_ADDENDUM = """

COACHING MODE — the student is a pre-clinical beginner practising medical English:
- Be warm, patient, and encouraging. Speak slowly and use short, simple, clear sentences.
- If the student goes quiet or seems stuck, gently prompt them in character, e.g.
  "Take your time, doctor." or offer a small nudge like "Did you want to ask how long I've had this?"
- If the student uses an unclear or slightly wrong word, respond to the meaning you think they intend
  rather than refusing to understand. Keep the conversation flowing.
- Keep your own turns short so the student does most of the talking.
- You may still hold back the hidden details until asked, but reveal them readily even when the
  question is imperfect. Never lecture, correct grammar, or step out of character.
"""

PRECLINICAL_GUIDANCE = """
LEARNER LEVEL — PRE-CLINICAL BEGINNER (read carefully):
This student is an early medical student who has NOT yet started clinical rotations.
At this stage the goal is MEDICAL ENGLISH and COMMUNICATION, not clinical workup.
- Focus scoring and feedback on language, vocabulary, pronunciation, and basic rapport.
- Do NOT penalize the absence of a differential diagnosis, investigations, or a management plan.
- Be encouraging and concrete. Name at least two specific things the student did well.
- Limit corrections to the 4-6 most useful items so the student is not overwhelmed.
- Make Anki cards teach high-frequency clinical phrases and everyday symptom vocabulary,
  not rare facts.
"""

OUTPUT_SCHEMA_INSTRUCTION = """
Return ONLY a valid JSON object. No preamble, no markdown fences, no explanation outside the JSON.
Schema (include ONLY keys listed in output_sections for this evaluation):

{{
  "overall_scores": {{
    "<metric_key>": <float 0-10>
  }},
  "self_assessment_delta": {{
    "<metric_key>": <float, claude_score - self_score>
  }},
  "checklist_results": [
    {{"item": "...", "required": true/false, "passed": true/false, "evidence": "quote or null"}}
  ],
  "history_completeness": <float 0.0-1.0>,
  "ice_elicited": <true/false>,
  "empathy_markers_found": ["marker1", "marker2"],
  "soap_note": {{
    "subjective": "...",
    "objective": "...",
    "assessment": "...",
    "plan": "..."
  }},
  "corrections": [
    {{
      "turn_index": <int>,
      "original": "...",
      "corrected": "...",
      "explanation": "..."
    }}
  ],
  "anki_cards": [
    {{
      "front": "...",
      "back": "...",
      "tags": ["medical-english", "<grammar|vocabulary|clinical-phrasing>"]
    }}
  ],
  "summary_feedback": "..."
}}

Required sections for this session: {sections_list}
Always include "summary_feedback".
Generate at least 3 Anki cards if "anki_cards" is in sections, focusing on language corrections and useful clinical phrases.
"""


COMPLEXITY_MODIFIERS = [
    "COMPLEXITY MODIFIER (Act this out subtly): You have a hidden agenda - you are secretly worried you might have a severe disease (like cancer), but you won't bring it up unless the doctor makes you feel very comfortable or asks directly about your fears.",
    "COMPLEXITY MODIFIER (Act this out subtly): You have low health literacy. You don't understand big medical words. If the doctor uses jargon, act confused or ask them to explain it simply.",
    "COMPLEXITY MODIFIER (Act this out subtly): You are defensive and slightly anxious because you had a bad experience with doctors in the past. Be a bit hesitant with your answers initially until the doctor builds rapport.",
    "COMPLEXITY MODIFIER (Act this out subtly): You are a 'yes' patient. You nod and say yes to everything to avoid looking foolish, even if you didn't really understand the doctor's explanation. The doctor needs to explicitly ask you to explain it back to verify your understanding."
]

def assign_complexity_modifier(case_data: dict) -> dict:
    """Return a per-session copy of the case, rolling the complexity modifier.

    The chosen modifier is stored ON the case (``active_complexity_modifier``)
    so it is persisted in the session's raw_case_json and the post-session
    evaluator knows the patient was role-playing that twist. Any modifier left
    over from a previous run of the same case is cleared before re-rolling.
    Coaching cases (beginners) and free-form personas (skill drills, handovers)
    never get a modifier.
    """
    case = dict(case_data)
    case.pop("active_complexity_modifier", None)
    if (not case.get("coaching_mode") and not case.get("persona_override")
            and random.random() < 0.4):
        case["active_complexity_modifier"] = random.choice(COMPLEXITY_MODIFIERS)
    return case


def build_patient_prompt(case_data: dict) -> str:
    # Skill drills supply their own free-form persona instead of the rigid
    # patient template (which assumes a clinical history-taking encounter).
    override = case_data.get("persona_override")
    if override:
        prompt = override.strip()
    else:
        prompt = PATIENT_SYSTEM_PROMPT.format(
            patient_name=case_data.get("patient_name", "the patient"),
            age=case_data.get("age", "unknown"),
            gender=case_data.get("gender", "unknown"),
            chief_complaint=case_data.get("chief_complaint", ""),
            hpi_details=case_data.get("hpi_details", ""),
            ideas=case_data.get("ideas", ""),
            concerns=case_data.get("concerns", ""),
            expectations=case_data.get("expectations", ""),
            pmh=case_data.get("pmh", "none"),
            medications=case_data.get("medications", "none"),
            social_hx=case_data.get("social_hx", "not provided"),
        )

    # Dynamic complexity (assigned per-session via assign_complexity_modifier)
    # to simulate real-world unpredictable patients.
    modifier = case_data.get("active_complexity_modifier")
    if modifier:
        prompt += f"\n\n{modifier}\n"

    if case_data.get("coaching_mode"):
        prompt += COACHING_ADDENDUM
    return prompt


def build_interview_prompt(scenario: dict) -> str:
    return INTERVIEW_SYSTEM_PROMPT.format(
        pd_name=scenario.get("pd_name", "Dr. Smith"),
        program=scenario.get("program", "this program"),
        category=scenario.get("category", "behavioral"),
        opening_question=scenario.get("opening_question", "Tell me about yourself."),
    )


def build_custom_prompt(persona_description: str) -> str:
    return CUSTOM_SYSTEM_PROMPT.format(
        user_defined_persona_description=persona_description
    )


def build_analysis_prompt(
    transcript: list[dict],
    case_data: dict,
    eval_data: dict,
    self_scores: dict | None = None,
    student_soap: dict | None = None,
) -> str:
    sections = eval_data.get("output_sections", [])
    parts = [ANALYSIS_BASE_HEADER]

    if eval_data.get("learner_level") == "preclinical":
        parts.append(PRECLINICAL_GUIDANCE)

    parts.append(f"""
CASE GROUND TRUTH (use this to assess what was elicited vs missed):
{json.dumps(case_data, indent=2, ensure_ascii=False)}
""")

    if case_data.get("active_complexity_modifier"):
        parts.append(
            "\nNOTE: During this session the simulated patient was secretly role-playing "
            "the following behavioral twist. Take it into account when judging the "
            "student's performance (e.g. reward detecting and adapting to it; do not "
            "penalize the student for information the patient deliberately withheld):\n"
            + case_data["active_complexity_modifier"]
        )

    transcript_text = "\n".join(
        f"[Turn {t['turn_index']}] {t['role'].upper()}: {t['text']}"
        for t in transcript
    )
    parts.append(f"\nTRANSCRIPT:\n{transcript_text}\n")

    if eval_data.get("metrics"):
        parts.append(
            "\nSCORING RUBRIC ANCHORS:\n"
            + json.dumps(eval_data["metrics"], indent=2, ensure_ascii=False)
        )

    if "checklist" in sections and eval_data.get("checklist"):
        parts.append(
            "\nCHECKLIST (evaluate each item against transcript):\n"
            + json.dumps(eval_data["checklist"], indent=2, ensure_ascii=False)
        )

    if "ice_empathy" in sections and eval_data.get("empathy_markers"):
        parts.append(
            "\nEMPATHY MARKERS TO DETECT:\n"
            + json.dumps(eval_data["empathy_markers"], indent=2, ensure_ascii=False)
        )

    if self_scores:
        parts.append(
            "\nSTUDENT SELF-ASSESSMENT (include delta in output for comparison):\n"
            + json.dumps(self_scores, indent=2)
        )

    if eval_data.get("custom_criteria_prose"):
        parts.append(
            f"\nADDITIONAL EVALUATION CRITERIA:\n{eval_data['custom_criteria_prose']}"
        )

    if student_soap:
        student_soap_str = json.dumps(student_soap, indent=2)
        parts.append(f"\n<STUDENT_SOAP>\nThe student wrote the following SOAP note. Compare it to your ideal SOAP note and include specific corrections for it in the `corrections` list.\n{student_soap_str}\n</STUDENT_SOAP>\n")

    SCHEMA_KEYS_MAP = {
        "scores": "overall_scores",
        "checklist": "checklist_results",
        "history_completeness": "history_completeness",
        "ice_empathy": ["ice_elicited", "empathy_markers_found"],
        "soap_note": "soap_note",
        "corrections": "corrections",
        "anki_cards": "anki_cards",
        "summary": "summary_feedback"
    }

    schema_keys = []
    for sec in sections:
        mapped = SCHEMA_KEYS_MAP.get(sec)
        if isinstance(mapped, list):
            schema_keys.extend(mapped)
        elif mapped:
            schema_keys.append(mapped)
        else:
            schema_keys.append(sec)

    parts.append(
        OUTPUT_SCHEMA_INSTRUCTION.format(sections_list=json.dumps(schema_keys))
    )

    return "\n".join(parts)
