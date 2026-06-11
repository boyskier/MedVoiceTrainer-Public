import json
import random
import time
from typing import Optional

import genanki


def _make_model() -> genanki.Model:
    return genanki.Model(
        1948271623,
        "MedVoiceTrainer Basic",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }],
    )


def export_sessions_to_apkg(sessions: list[dict], output_path: str) -> Optional[str]:
    """Export Anki cards from one or more sessions to an .apkg file.

    Returns the output path, or None when the sessions contained no cards
    (in which case no file is written — callers should tell the user instead
    of claiming a deck was saved)."""
    model = _make_model()
    notes = []

    for session in sessions:
        analysis = {}
        if session.get("raw_claude_response"):
            try:
                analysis = json.loads(session["raw_claude_response"])
            except Exception:
                pass
        if not analysis and session.get("anki_cards"):
            try:
                analysis["anki_cards"] = json.loads(session["anki_cards"])
            except Exception:
                pass

        cards = analysis.get("anki_cards", [])
        created_at = session.get("created_at", "")[:10]
        mode = session.get("mode", "session")

        for card in cards:
            clean_tags = [t.replace(" ", "_") for t in card.get("tags", [])]
            clean_mode = mode.replace(" ", "_")
            tags = clean_tags + [f"mvt-{clean_mode}", f"date-{created_at}"]
            note = genanki.Note(
                model=model,
                fields=[card.get("front", ""), card.get("back", "")],
                tags=tags,
            )
            notes.append(note)

    if not notes:
        return None

    # Use a stable deck ID to prevent polluting Anki with multiple decks of the same name on repeated exports
    deck_id = 1948271624
    deck_name = f"MedVoiceTrainer::{time.strftime('%Y-%m-%d')}"
    deck = genanki.Deck(deck_id, deck_name)
    for note in notes:
        deck.add_note(note)

    package = genanki.Package(deck)
    package.write_to_file(output_path)
    return output_path
