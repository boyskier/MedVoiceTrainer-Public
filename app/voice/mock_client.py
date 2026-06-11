import asyncio
import queue
from typing import Optional

from app.voice.base_client import VoiceClient

MOCK_PATIENT_LINES = [
    "Hello, doctor. I've been having this chest pain since this morning and it's really worrying me.",
    "It's in the middle of my chest, quite severe, maybe a 7 out of 10. It doesn't really go anywhere specific.",
    "It started while I was just sitting watching TV. Nothing special was happening.",
    "My dad actually died of a heart attack when he was 62, so I'm honestly quite scared this might be the same thing.",
    "I thought it might be heartburn at first, so I took some antacids but they didn't help at all.",
    "I do smoke, yes. About a pack a day for the last 20 years. I know, I know...",
    "I have high blood pressure and diabetes. I take metformin and lisinopril.",
    "Honestly, I just want to know if it's serious and if there's something you can give me for the pain.",
    "Thank you doctor. I appreciate you explaining everything to me.",
]

MOCK_INTERVIEW_LINES = [
    "Thank you for coming in today. Before we start formally, can I ask — how are you feeling?",
    "Interesting background. Can you elaborate on what specifically drew you to internal medicine over other specialties?",
    "That's a compelling reason. Tell me about a challenging clinical case you managed — walk me through your thinking.",
    "Good. And how did you communicate that uncertainty to the patient?",
    "What would your peers say is your biggest area for development as a clinician?",
    "Fair enough. Why this program specifically? What do you know about us?",
    "Any questions for me about the program?",
]


class MockVoiceClient(VoiceClient):
    def __init__(self, ui_queue: queue.Queue, mode: str = "encounter"):
        super().__init__(ui_queue)
        self.mode = mode
        self._running = False
        self._turn_index = 0
        self._lines = MOCK_INTERVIEW_LINES if mode == "interview" else MOCK_PATIENT_LINES

    async def connect(self, system_prompt: str, voice_config: dict) -> None:
        self._running = True
        self._turn_index = 0
        self.emit({"type": "status", "text": "DEV MODE — mock session started"})
        asyncio.create_task(self._feed_lines())

    async def _feed_lines(self) -> None:
        role = "interviewer" if self.mode == "interview" else "patient"
        for line in self._lines:
            if not self._running:
                break
            await asyncio.sleep(2.5)
            self.emit({
                "type": "transcript",
                "role": role,
                "turn_index": self._turn_index,
                "text": line,
            })
            self._turn_index += 1
        if self._running:
            await asyncio.sleep(2.0)
            self.emit({"type": "session_end"})

    async def send_audio_chunk(self, chunk: bytes) -> None:
        pass

    async def close(self) -> None:
        self._running = False
        self.emit({"type": "status", "text": "Mock session closed"})

    def emit_user_turn(self, text: str) -> None:
        self.emit({
            "type": "transcript",
            "role": "user",
            "turn_index": self._turn_index,
            "text": text,
        })
        self._turn_index += 1


MOCK_ANALYSIS_RESULT = {
    "overall_scores": {
        "grammar": 7.5,
        "medical_accuracy": 8.0,
        "clinical_reasoning": 7.0,
        "communication_fluency": 6.5,
    },
    "checklist_results": [
        {"item": "onset and duration elicited", "required": True, "passed": True, "evidence": "asked about when it started"},
        {"item": "character and severity (1-10 scale)", "required": True, "passed": True, "evidence": "asked severity 1 to 10"},
        {"item": "radiation or spread asked", "required": True, "passed": True, "evidence": "asked if it goes anywhere"},
        {"item": "alleviating and aggravating factors", "required": True, "passed": True, "evidence": "asked about antacids"},
        {"item": "associated symptoms explored", "required": True, "passed": False, "evidence": None},
        {"item": "ICE explored — ideas", "required": True, "passed": True, "evidence": "asked what patient thinks is going on"},
        {"item": "ICE explored — concerns", "required": True, "passed": True, "evidence": "explored fear of heart attack"},
        {"item": "ICE explored — expectations", "required": True, "passed": False, "evidence": None},
    ],
    "history_completeness": 0.72,
    "ice_elicited": True,
    "empathy_markers_found": [
        "acknowledged patient concern explicitly",
        "used patient's name at least once",
    ],
    "soap_note": {
        "subjective": "58M with 2hr substernal chest pain 7/10, non-radiating, onset at rest, no relief with antacids. Hx: HTN, T2DM, 20 pack-yr smoker. FHx: father MI at 62.",
        "objective": "Pending examination and investigations (ECG, troponins, CXR).",
        "assessment": "ACS until proven otherwise. DDx: STEMI/NSTEMI, unstable angina, aortic dissection.",
        "plan": "ECG, troponin x2, aspirin 325mg, IV access, cardiology consult, NPO.",
    },
    "corrections": [
        {
            "turn_index": 2,
            "original": "Can you tell me about the pain, where exactly is it?",
            "corrected": "Could you describe the pain for me — where exactly do you feel it?",
            "explanation": "More open-ended phrasing invites a fuller patient narrative. 'Could you describe' is softer and more patient-centred than 'Can you tell me about'.",
        }
    ],
    "anki_cards": [
        {
            "front": "What is the SOCRATES mnemonic used for in history-taking?",
            "back": "Site, Onset, Character, Radiation, Associations, Time/duration, Exacerbating/relieving factors, Severity",
            "tags": ["medical-english", "clinical-phrasing"],
        },
        {
            "front": "How do you ask about ICE in a clinical encounter?",
            "back": "Ideas: 'What do you think might be causing this?' / Concerns: 'What worries you most about this?' / Expectations: 'What were you hoping we might do for you today?'",
            "tags": ["medical-english", "clinical-phrasing"],
        },
        {
            "front": "Give a natural phrase to transition to asking about social history.",
            "back": "'I'd like to ask a few questions about your lifestyle, if that's okay. Do you smoke or drink alcohol?'",
            "tags": ["medical-english", "vocabulary"],
        },
    ],
    "summary_feedback": (
        "Good systematic approach to the chest pain history. Strengths: you explored ICE effectively and showed empathy towards the patient's fear of a heart attack. "
        "Areas for improvement: remember to explore associated symptoms more fully (nausea, diaphoresis, dyspnoea) and always close by asking about the patient's expectations. "
        "Your medical terminology was accurate and your communication was mostly fluent — work on reducing filler phrases like 'um' and 'so'. "
        "For a patient presenting with possible ACS, always verbalize your priority differential early in the encounter."
    ),
}
