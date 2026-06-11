import json
from datetime import datetime, timezone
from typing import Optional, Any

from app.db.database import get_connection, backup_db


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
        (key, value, datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
    )
    conn.commit()
    conn.close()


def create_session(
    mode: str,
    case_name: str,
    case_id: Optional[str],
    eval_template: Optional[str],
    voice_backend: str,
    raw_case_json: dict,
    raw_eval_json: Optional[dict],
) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO sessions
        (created_at, mode, case_name, case_id, eval_template, voice_backend,
         raw_transcript, raw_case_json, raw_eval_json)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            mode,
            case_name,
            case_id,
            eval_template,
            voice_backend,
            json.dumps([]),
            json.dumps(raw_case_json),
            json.dumps(raw_eval_json) if raw_eval_json else None,
        ),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def append_turn(session_id: int, turn: dict) -> None:
    """Persist a single transcript turn immediately (never lose data)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT raw_transcript FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row:
        turns = json.loads(row["raw_transcript"])
        turns.append(turn)
        conn.execute(
            "UPDATE sessions SET raw_transcript=? WHERE id=?",
            (json.dumps(turns), session_id),
        )
        conn.commit()
    conn.close()


def _pick(d: dict, *keys):
    """Return the first key whose value is present (not None), preserving 0.0."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def finalize_session(session_id: int, duration_seconds: int, analysis: dict) -> None:
    scores = analysis.get("overall_scores") or {}
    soap = analysis.get("soap_note")
    conn = get_connection()
    conn.execute(
        """UPDATE sessions SET
            duration_seconds=?,
            raw_claude_response=?,
            grammar_score=?,
            medical_accuracy_score=?,
            clinical_reasoning_score=?,
            professionalism_score=?,
            fluency_score=?,
            checklist_results=?,
            history_completeness=?,
            ice_elicited=?,
            empathy_markers_found=?,
            soap_note=?,
            corrections=?,
            anki_cards=?,
            summary_feedback=?
        WHERE id=?""",
        (
            duration_seconds,
            json.dumps(analysis),
            scores.get("grammar"),
            scores.get("medical_accuracy"),
            scores.get("clinical_reasoning"),
            scores.get("professionalism"),
            _pick(scores, "communication_fluency", "fluency"),
            json.dumps(analysis.get("checklist_results")) if analysis.get("checklist_results") is not None else None,
            analysis.get("history_completeness"),
            # NULL when the eval had no ICE section — 0 would falsely record
            # "failed to elicit ICE" for e.g. interview sessions.
            (1 if analysis["ice_elicited"] else 0) if "ice_elicited" in analysis else None,
            json.dumps(analysis.get("empathy_markers_found")) if analysis.get("empathy_markers_found") is not None else None,
            json.dumps(soap) if soap else None,
            json.dumps(analysis.get("corrections")) if analysis.get("corrections") is not None else None,
            json.dumps(analysis.get("anki_cards")) if analysis.get("anki_cards") is not None else None,
            analysis.get("summary_feedback"),
            session_id,
        ),
    )
    conn.commit()
    conn.close()
    backup_db(session_id)


def save_cost_data(
    session_id: int,
    claude_input: int,
    claude_output: int,
    claude_cached: int,
    claude_cost: float,
    voice_cost: float,
    total_cost: float,
    report_path: Optional[str] = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE sessions SET
            claude_input_tokens=?, claude_output_tokens=?, claude_cached_tokens=?,
            claude_cost_usd=?, voice_cost_usd=?, total_cost_usd=?, cost_report_path=?
        WHERE id=?""",
        (claude_input, claude_output, claude_cached,
         claude_cost, voice_cost, total_cost, report_path,
         session_id),
    )
    conn.commit()
    conn.close()


def save_self_scores(session_id: int, self_scores: dict) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE sessions SET
            self_grammar=?, self_medical_accuracy=?,
            self_clinical_reasoning=?, self_professionalism=?, self_fluency=?
        WHERE id=?""",
        (
            self_scores.get("grammar"),
            self_scores.get("medical_accuracy"),
            self_scores.get("clinical_reasoning"),
            self_scores.get("professionalism"),
            _pick(self_scores, "communication_fluency", "fluency"),
            session_id,
        ),
    )
    conn.commit()
    conn.close()


def save_student_soap(session_id: int, soap_text: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE sessions SET student_soap_note=? WHERE id=?", (soap_text, session_id))
    conn.commit()
    conn.close()


def save_debrief_chat(session_id: int, chat_json: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE sessions SET debrief_chat=? WHERE id=?", (chat_json, session_id))
    conn.commit()
    conn.close()


def save_docx_path(session_id: int, path: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE sessions SET docx_path=? WHERE id=?", (path, session_id))
    conn.commit()
    conn.close()


def get_session(session_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_sessions(limit: int = 200) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sessions_for_case(case_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE case_id=? ORDER BY created_at DESC",
        (case_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_session(session_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()

def finalize_empty_session(session_id: int, duration_seconds: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET duration_seconds=? WHERE id=?",
        (duration_seconds, session_id),
    )
    conn.commit()
    conn.close()
