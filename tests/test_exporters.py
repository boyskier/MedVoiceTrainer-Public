"""Tests for app/export/docx_exporter.py and app/export/anki_exporter.py."""
import json
import os
import shutil
import tempfile
import unittest


MINIMAL_SESSION = {
    "id": 1,
    "created_at": "2026-06-02T10:30:00",
    "mode": "encounter",
    "case_name": "Mr. Test",
    "case_id": "cardio_001",
    "eval_template": "history_taking",
    "voice_backend": "mock",
    "duration_seconds": 180,
    "self_grammar": 6.0,
    "self_medical_accuracy": 5.5,
    "self_clinical_reasoning": 7.0,
    "self_fluency": 6.5,
    "grammar_score": 7.5,
    "medical_accuracy_score": 8.0,
    "clinical_reasoning_score": 7.0,
    "fluency_score": 6.5,
    "raw_transcript": json.dumps([
        {"turn_index": 0, "role": "patient", "text": "Hello doctor."},
        {"turn_index": 1, "role": "user", "text": "What brings you in today?"},
    ]),
    "raw_case_json": json.dumps({
        "id": "cardio_001",
        "reference_soap": {
            "subjective": "58M with chest pain",
            "objective": "ECG needed",
            "assessment": "ACS",
            "plan": "Aspirin, ECG",
        }
    }),
    "raw_eval_json": None,
    "raw_claude_response": json.dumps({
        "overall_scores": {
            "grammar": 7.5,
            "medical_accuracy": 8.0,
            "clinical_reasoning": 7.0,
            "communication_fluency": 6.5,
        },
        "self_assessment_delta": {"grammar": 1.5, "medical_accuracy": 2.5},
        "checklist_results": [
            {"item": "onset and duration", "required": True, "passed": True, "evidence": "asked timing"},
            {"item": "ICE explored", "required": True, "passed": False, "evidence": None},
        ],
        "soap_note": {
            "subjective": "Patient reports chest pain.",
            "objective": "ECG pending.",
            "assessment": "ACS query.",
            "plan": "Aspirin, monitor.",
        },
        "corrections": [
            {
                "turn_index": 1,
                "original": "What is the pain?",
                "corrected": "Could you describe the pain for me?",
                "explanation": "More open-ended phrasing.",
            }
        ],
        "anki_cards": [
            {"front": "What does SOCRATES stand for?",
             "back": "Site, Onset, Character, Radiation, Associations, Time, Exacerbating/relieving, Severity",
             "tags": ["medical-english", "clinical-phrasing"]},
        ],
        "summary_feedback": "Good job overall. Work on ICE elicitation.",
    }),
}


class TestDocxExporter(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generates_file(self):
        from app.export.docx_exporter import generate_report
        out = os.path.join(self.tmpdir, "report.docx")
        result = generate_report(MINIMAL_SESSION, out)
        self.assertTrue(os.path.exists(result))

    def test_file_is_nonzero_size(self):
        from app.export.docx_exporter import generate_report
        out = os.path.join(self.tmpdir, "report.docx")
        generate_report(MINIMAL_SESSION, out)
        self.assertGreater(os.path.getsize(out), 1000)

    def test_returns_output_path(self):
        from app.export.docx_exporter import generate_report
        out = os.path.join(self.tmpdir, "report.docx")
        result = generate_report(MINIMAL_SESSION, out)
        self.assertEqual(result, out)

    def test_valid_docx_structure(self):
        """The file should be a valid zip (docx is a zip)."""
        import zipfile
        from app.export.docx_exporter import generate_report
        out = os.path.join(self.tmpdir, "report.docx")
        generate_report(MINIMAL_SESSION, out)
        self.assertTrue(zipfile.is_zipfile(out))

    def test_docx_contains_text_content(self):
        """Word document must contain expected text in the XML."""
        import zipfile
        from app.export.docx_exporter import generate_report
        out = os.path.join(self.tmpdir, "report.docx")
        generate_report(MINIMAL_SESSION, out)
        with zipfile.ZipFile(out) as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")
        self.assertIn("MedVoiceTrainer", doc_xml)
        self.assertIn("Mr. Test", doc_xml)

    def test_minimal_session_no_analysis_does_not_crash(self):
        """Sessions without raw_claude_response should still produce a file."""
        from app.export.docx_exporter import generate_report
        session = dict(MINIMAL_SESSION, raw_claude_response=None)
        out = os.path.join(self.tmpdir, "minimal.docx")
        generate_report(session, out)
        self.assertTrue(os.path.exists(out))

    def test_suggest_filename_format(self):
        from app.export.docx_exporter import suggest_filename
        name = suggest_filename(MINIMAL_SESSION)
        self.assertTrue(name.endswith(".docx"))
        self.assertIn("20260602", name)
        self.assertIn("encounter", name)
        self.assertIn("Mr", name)

    def test_suggest_filename_handles_missing_fields(self):
        from app.export.docx_exporter import suggest_filename
        name = suggest_filename({})
        self.assertTrue(name.endswith(".docx"))

    def test_suggest_filename_sanitises_slashes(self):
        from app.export.docx_exporter import suggest_filename
        session = dict(MINIMAL_SESSION, case_name="GI/Bleeding")
        name = suggest_filename(session)
        self.assertNotIn("/", name)

    def test_docx_contains_correct_self_assessment_scores(self):
        from app.export.docx_exporter import generate_report
        import zipfile
        session = dict(MINIMAL_SESSION)
        session["self_professionalism"] = 9.5
        session["self_clinical_reasoning"] = 4.0
        session["raw_claude_response"] = json.dumps({
            "overall_scores": {
                "clinical_reasoning": 8.0,
                "professionalism": 9.0
            }
        })
        out = os.path.join(self.tmpdir, "score_test.docx")
        generate_report(session, out)
        with zipfile.ZipFile(out) as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")
        self.assertIn("9.5", doc_xml)
        self.assertIn("4.0", doc_xml)


    def test_docx_invalid_created_at(self):
        from app.export.docx_exporter import generate_report
        session = dict(MINIMAL_SESSION, created_at="invalid-date")
        out = os.path.join(self.tmpdir, "date_test.docx")
        generate_report(session, out)
        self.assertTrue(os.path.exists(out))

    def test_docx_invalid_raw_claude_response_json(self):
        from app.export.docx_exporter import generate_report
        session = dict(MINIMAL_SESSION, raw_claude_response="invalid-json")
        out = os.path.join(self.tmpdir, "json_test.docx")
        generate_report(session, out)
        self.assertTrue(os.path.exists(out))

    def test_docx_invalid_raw_case_json(self):
        from app.export.docx_exporter import generate_report
        session = dict(MINIMAL_SESSION, raw_case_json="invalid-json", reference_soap=None)
        out = os.path.join(self.tmpdir, "case_test.docx")
        generate_report(session, out)
        self.assertTrue(os.path.exists(out))

    def test_docx_invalid_reference_soap_json(self):
        from app.export.docx_exporter import generate_report
        session = dict(MINIMAL_SESSION, reference_soap="invalid-json", raw_case_json=None)
        out = os.path.join(self.tmpdir, "soap_test.docx")
        generate_report(session, out)
        self.assertTrue(os.path.exists(out))


class TestAnkiExporter(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generates_apkg_file(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        out = os.path.join(self.tmpdir, "deck.apkg")
        export_sessions_to_apkg([MINIMAL_SESSION], out)
        self.assertTrue(os.path.exists(out))

    def test_apkg_is_valid_zip(self):
        import zipfile
        from app.export.anki_exporter import export_sessions_to_apkg
        out = os.path.join(self.tmpdir, "deck.apkg")
        export_sessions_to_apkg([MINIMAL_SESSION], out)
        self.assertTrue(zipfile.is_zipfile(out))

    def test_apkg_nonzero_size(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        out = os.path.join(self.tmpdir, "deck.apkg")
        export_sessions_to_apkg([MINIMAL_SESSION], out)
        self.assertGreater(os.path.getsize(out), 500)

    def test_multi_session_export(self):
        """Export two sessions at once — should not raise."""
        from app.export.anki_exporter import export_sessions_to_apkg
        out = os.path.join(self.tmpdir, "multi.apkg")
        export_sessions_to_apkg([MINIMAL_SESSION, MINIMAL_SESSION], out)
        self.assertTrue(os.path.exists(out))

    def test_empty_sessions_list_does_not_crash(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        out = os.path.join(self.tmpdir, "empty.apkg")
        export_sessions_to_apkg([], out)
        # File may or may not be created — but no exception

    def test_session_with_no_anki_cards(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION)
        raw = json.loads(session["raw_claude_response"])
        raw["anki_cards"] = []
        session["raw_claude_response"] = json.dumps(raw)
        out = os.path.join(self.tmpdir, "nocards.apkg")
        export_sessions_to_apkg([session], out)
        # Should not crash even with no cards

    def test_session_anki_from_raw_anki_cards_column(self):
        """If raw_claude_response is None, should fall back to anki_cards column."""
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION, raw_claude_response=None)
        session["anki_cards"] = json.dumps([
            {"front": "Q", "back": "A", "tags": ["medical-english"]}
        ])
        out = os.path.join(self.tmpdir, "fallback.apkg")
        export_sessions_to_apkg([session], out)
        self.assertTrue(os.path.exists(out))

    def test_anki_deck_id_is_stable(self):
        """Verify that running export_sessions_to_apkg results in a stable deck ID (1948271624)."""
        import zipfile
        import sqlite3
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION)
        out = os.path.join(self.tmpdir, "deck_test.apkg")
        export_sessions_to_apkg([session], out)
        self.assertTrue(zipfile.is_zipfile(out))
        with zipfile.ZipFile(out) as zf:
            zf.extract("collection.anki2", self.tmpdir)
        db_path = os.path.join(self.tmpdir, "collection.anki2")
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT decks FROM col").fetchone()
        decks_json = json.loads(row[0])
        conn.close()
        self.assertIn("1948271624", decks_json)

    def test_anki_tags_are_sanitized(self):
        """Verify that tags containing spaces are sanitized to use underscores."""
        import zipfile
        import sqlite3
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION, mode="patient encounter")
        session["raw_claude_response"] = json.dumps({
            "anki_cards": [
                {"front": "Q", "back": "A", "tags": ["medical jargon", "some tag"]}
            ]
        })
        out = os.path.join(self.tmpdir, "tags_test.apkg")
        export_sessions_to_apkg([session], out)
        self.assertTrue(zipfile.is_zipfile(out))
        with zipfile.ZipFile(out) as zf:
            zf.extract("collection.anki2", self.tmpdir)
        db_path = os.path.join(self.tmpdir, "collection.anki2")
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT tags FROM notes LIMIT 1").fetchone()
        conn.close()
        tags_str = row[0]
        tags = tags_str.strip().split(" ")
        self.assertIn("medical_jargon", tags)
        self.assertIn("some_tag", tags)
        self.assertIn("mvt-patient_encounter", tags)
        self.assertNotIn("medical", tags)
        self.assertNotIn("jargon", tags)

    def test_anki_exporter_invalid_claude_json(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION, raw_claude_response="invalid-json", anki_cards="[]")
        out = os.path.join(self.tmpdir, "invalid_claude.apkg")
        export_sessions_to_apkg([session], out)

    def test_anki_exporter_invalid_anki_cards_json(self):
        from app.export.anki_exporter import export_sessions_to_apkg
        session = dict(MINIMAL_SESSION, raw_claude_response=None, anki_cards="invalid-json")
        out = os.path.join(self.tmpdir, "invalid_anki.apkg")
        export_sessions_to_apkg([session], out)


if __name__ == "__main__":
    unittest.main()
