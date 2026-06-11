"""
Builds a personalised 'Practice My Mistakes' session from the user's own history.

Pipeline:
1. Pull past sessions from the DB (most recent first).
2. Aggregate their `corrections` into a deduplicated, frequency-ranked list of
   target items (the improved phrases the student should now produce).
3. Construct a DYNAMIC case (free-form `persona_override`) + a runtime eval whose
   checklist has one item per target, so the normal voice + analysis + feedback
   machinery scores each target with no special-casing downstream.

Mode A (interactive): the coach AI sets up fresh situations that prompt the
student to say the improved form OUT LOUD, without revealing the answer.
"""
import json
import os
from collections import OrderedDict

import config

MIN_TARGETS = 3
MAX_TARGETS = 6
SESSION_LOOKBACK = 50


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def aggregate_corrections(sessions: list[dict], max_items: int = MAX_TARGETS) -> list[dict]:
    """Collapse the `corrections` across sessions into ranked target items.

    `sessions` is expected most-recent-first (as returned by list_sessions), so
    insertion order encodes recency and is preserved as the tie-breaker by the
    stable sort below. Items are keyed by their normalized `corrected` text.
    """
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for sess in sessions:
        raw = sess.get("corrections")
        if not raw:
            continue
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        if not isinstance(items, list):
            continue
        for c in items:
            if not isinstance(c, dict):
                continue
            corrected = (c.get("corrected") or "").strip()
            if not corrected:
                continue
            key = _norm(corrected)
            if key not in groups:
                groups[key] = {
                    "original": (c.get("original") or "").strip(),
                    "corrected": corrected,
                    "explanation": (c.get("explanation") or "").strip(),
                    "count": 0,
                }
            groups[key]["count"] += 1
    ranked = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    return ranked[:max_items]


def prepare_targets(max_items: int = MAX_TARGETS) -> list[dict]:
    """Convenience: read recent sessions from the DB and aggregate them."""
    from app.db import queries
    sessions = queries.list_sessions(limit=SESSION_LOOKBACK)
    return aggregate_corrections(sessions, max_items=max_items)


def _build_persona(targets: list[dict]) -> str:
    lines = []
    for i, t in enumerate(targets, 1):
        line = f'{i}. was: "{t["original"]}"  ->  aim: "{t["corrected"]}"'
        if t.get("explanation"):
            line += f'  (why: {t["explanation"]})'
        lines.append(line)
    target_block = "\n".join(lines)
    return (
        "You are a friendly clinical-English coach running a PERSONALISED REVIEW for a "
        "beginner medical student.\n"
        "The student previously made the language errors listed below. Create short, natural "
        "practice moments that prompt the student to PRODUCE the improved version OUT LOUD — "
        "without telling them the answer first.\n\n"
        "TARGET ITEMS (the student should now produce the improved form):\n"
        f"{target_block}\n\n"
        "Rules:\n"
        "- Each turn, role-play ONE realistic situation (usually as a patient) that naturally "
        "calls for one target item, then pause and wait for the student.\n"
        "- Do NOT say the improved phrase yourself. Let the student attempt it.\n"
        "- If they produce it well, briefly praise and move to the next item.\n"
        "- If they miss it or fall back into the old form, give a SMALL hint (not the full "
        "answer) and let them try again.\n"
        "- Cover every target item at least once, then revisit any they struggled with.\n"
        "- Keep your turns short. The session ends when the student says "
        '"I\'d like to end the session."'
    )


def build_review_case(targets: list[dict]) -> dict:
    """A dynamic case object compatible with EncounterTab / SessionBase."""
    return {
        "id": "review_corrections",
        "system": "review",
        "difficulty": "beginner",
        "eval_template": "correction_review",
        "learner_level": "preclinical",
        "coaching_mode": True,
        "patient_name": "My Mistakes Review",
        "chief_complaint": "personalised review of your past corrections",
        "persona_override": _build_persona(targets),
        "target_corrections": targets,
        "suggested_questions": [],
        "phrase_categories": [
            {
                "name": "Aim for these improved phrases",
                "phrases": [t["corrected"] for t in targets],
            }
        ],
    }


def build_review_eval(targets: list[dict]) -> dict:
    """Load the base eval and inject one checklist item per target."""
    path = os.path.join(config.EVAL_DIR, "correction_review.json")
    with open(path, encoding="utf-8") as f:
        ev = dict(json.load(f))
    ev["checklist"] = [
        {"item": f'used the improved form: "{t["corrected"]}"', "required": True}
        for t in targets
    ]
    return ev
