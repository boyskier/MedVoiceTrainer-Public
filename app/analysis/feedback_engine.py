import json
import os
import traceback
from typing import Optional

from app.analysis.prompt_builder import build_analysis_prompt
from app.db.database import log_event


def _resolve_feedback_backend() -> str:
    """Return the user-selected feedback provider, defaulting to Claude.

    Guarded so a missing/uninitialized settings DB (e.g. in unit tests) falls
    back to Claude rather than raising.
    """
    try:
        from app.db.queries import get_setting
        backend = get_setting("feedback_backend", "claude")
    except Exception:
        backend = "claude"
    if backend not in ("claude", "gemini", "openai"):
        backend = "claude"
    return backend


def run_analysis(
    transcript: list[dict],
    case_data: dict,
    eval_data: dict,
    self_scores: Optional[dict] = None,
    session_id: Optional[int] = None,
    student_soap: Optional[dict] = None,
    duration_seconds: Optional[int] = None,
) -> dict:
    """Run post-session analysis and return a parsed analysis dict.

    The provider (Claude / Gemini / OpenAI) is chosen by the user's
    ``feedback_backend`` setting — the logic and output schema are identical
    across providers. Raises on failure.

    After a successful call, automatically:
      - computes token cost
      - saves cost data to the sessions table
      - writes a cost_report_*.txt file next to sessions.db
    """
    from app.analysis.analysis_providers import call_analysis

    backend = _resolve_feedback_backend()
    prompt = build_analysis_prompt(transcript, case_data, eval_data, self_scores, student_soap)

    try:
        raw_text, usage = call_analysis(backend, prompt)
    except ValueError:
        # Missing API key / SDK — surface the actionable message unchanged.
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        log_event("ERROR", f"{backend} analysis API call failed: {exc}",
                  session_id=session_id, traceback_str=tb)
        raise

    # Extract JSON block even if there is preceding/trailing text or markdown fences
    import re
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        raw_text = match.group(0)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        log_event(
            "ERROR",
            f"Failed to parse {backend} response as JSON: {exc}",
            session_id=session_id,
            traceback_str=raw_text[:2000],
        )
        raise ValueError(f"{backend} returned invalid JSON: {exc}\n\nRaw: {raw_text[:500]}")

    # Compute the self-assessment delta deterministically instead of trusting
    # the model's arithmetic (or its memory to include the section at all).
    # Calibration feedback is only useful if the numbers are exact.
    if self_scores and isinstance(result.get("overall_scores"), dict):
        delta = _compute_self_delta(result["overall_scores"], self_scores)
        if delta:
            result["self_assessment_delta"] = delta

    # ── Cost tracking ──────────────────────────────────────────────────────
    _record_cost(backend, usage, session_id, transcript, case_data, eval_data, duration_seconds)

    return result


def _compute_self_delta(ai_scores: dict, self_scores: dict) -> dict:
    """Per-metric (AI score − self score), tolerant of the fluency-key alias."""
    delta = {}
    for key, ai_val in ai_scores.items():
        try:
            ai_f = float(ai_val)
        except (TypeError, ValueError):
            continue
        self_val = self_scores.get(key)
        if self_val is None and key in ("fluency", "communication_fluency"):
            self_val = self_scores.get(
                "communication_fluency" if key == "fluency" else "fluency"
            )
        if self_val is None:
            continue
        try:
            delta[key] = round(ai_f - float(self_val), 1)
        except (TypeError, ValueError):
            continue
    return delta


def _record_cost(
    backend: str,
    usage: dict,
    session_id: Optional[int],
    transcript: list[dict],
    case_data: dict,
    eval_data: dict,
    duration_seconds: Optional[int] = None,
) -> None:
    """Compute cost, save to DB, and write cost_report txt file."""
    try:
        from app.analysis.cost_tracker import (
            build_report_from_session,
            save_cost_report,
            format_report_text,
        )
        from app.db.queries import get_session, save_cost_data
        import config

        session = get_session(session_id) if session_id else {}
        session_for_report = dict(session or {})
        session_for_report["raw_transcript"] = json.dumps(transcript)
        session_for_report["raw_case_json"] = json.dumps(case_data)
        session_for_report["raw_eval_json"] = json.dumps(eval_data)
        # The session row is not finalized yet, so its duration_seconds is still
        # NULL at this point; use the value passed from the live session so the
        # voice-cost estimate (which is per-second) is not computed against zero.
        if duration_seconds is not None:
            session_for_report["duration_seconds"] = duration_seconds

        report = build_report_from_session(
            session_for_report, analysis_provider=backend, analysis_usage=usage
        )

        # Save report file next to sessions.db
        report_dir = os.path.join(config.BASE_DIR, "db", "cost_reports")
        report_path = save_cost_report(report, report_dir)

        # Persist to DB
        if session_id:
            save_cost_data(
                session_id,
                claude_input=report.claude_input_tokens,
                claude_output=report.claude_output_tokens,
                claude_cached=report.claude_cached_input_tokens,
                claude_cost=report.claude_cost_usd,
                voice_cost=report.voice_cost_usd,
                total_cost=report.total_cost_usd,
                report_path=report_path,
            )

        log_event("INFO",
                  f"Cost report saved: total=${report.total_cost_usd:.6f} → {report_path}",
                  session_id=session_id)
    except Exception as exc:
        # Cost tracking must never crash the main analysis flow
        log_event("WARNING", f"Cost tracking failed (non-fatal): {exc}", session_id=session_id)


class MockAnalysisEngine:
    """Returns hardcoded analysis for dev mode; also writes a mock cost report."""

    @staticmethod
    def run(
        transcript: list[dict],
        case_data: dict,
        eval_data: dict,
        self_scores: Optional[dict] = None,
        session_id: Optional[int] = None,
        student_soap: Optional[dict] = None,
        duration_seconds: Optional[int] = None,
    ) -> dict:
        from app.voice.mock_client import MOCK_ANALYSIS_RESULT
        import copy
        result = copy.deepcopy(MOCK_ANALYSIS_RESULT)
        if self_scores:
            delta = {}
            for k, v in result.get("overall_scores", {}).items():
                self_val = self_scores.get(k, 5.0)
                delta[k] = round(v - self_val, 1)
            result["self_assessment_delta"] = delta

        # Write a mock cost report so the file is always generated in dev mode too
        MockAnalysisEngine._write_mock_cost_report(session_id, transcript, duration_seconds)
        return result

    @staticmethod
    def _write_mock_cost_report(
        session_id: Optional[int],
        transcript: list[dict],
        duration_seconds: Optional[int] = None,
    ) -> None:
        try:
            from app.analysis.cost_tracker import (
                SessionCostReport, format_report_text, save_cost_report
            )
            from app.db.queries import get_session, save_cost_data
            import config

            session = get_session(session_id) if session_id else {}
            report = SessionCostReport(
                session_id=session_id,
                created_at=(session or {}).get("created_at", ""),
                mode=(session or {}).get("mode", "encounter"),
                case_name=(session or {}).get("case_name", "mock"),
                voice_backend="mock",
                duration_seconds=duration_seconds or (session or {}).get("duration_seconds") or 60,
                claude_input_tokens=0,
                claude_output_tokens=0,
                claude_cached_input_tokens=0,
                claude_cost_usd=0.0,
                voice_cost_usd=0.0,
                total_cost_usd=0.0,
                notes=["DEV MODE — mock session, no actual API calls made. Cost = $0.00"],
            )
            report_dir = os.path.join(config.BASE_DIR, "db", "cost_reports")
            report_path = save_cost_report(report, report_dir)

            if session_id:
                save_cost_data(session_id, 0, 0, 0, 0.0, 0.0, 0.0, report_path)
        except Exception:
            pass
