"""
Token counting and API cost tracking for a single session.

Tracks:
  - Claude API (Anthropic) — analysis call
  - Gemini Live (estimated from transcript chars, billed per second of audio)
  - OpenAI Realtime (estimated from transcript tokens, billed per token)

Pricing constants are current as of 2025-Q4. Update if rates change.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── Anthropic Claude pricing (per 1M tokens, USD) ────────────────────────────
# claude-sonnet-4-6 (the analysis model)
CLAUDE_INPUT_PRICE_PER_1M = 3.00
CLAUDE_OUTPUT_PRICE_PER_1M = 15.00

# ── Non-Claude analysis (text) pricing (per 1M tokens, USD) ──────────────────
# Used when the user selects Gemini or OpenAI as the feedback backend.
# These are approximate as of 2026-Q2 — update if rates change. Output tokens
# include any hidden reasoning tokens these models spend.
# gemini-3.5-flash (text analysis call)
GEMINI_ANALYSIS_INPUT_PRICE_PER_1M = 0.50
GEMINI_ANALYSIS_OUTPUT_PRICE_PER_1M = 3.00
# gpt-5.1 (text analysis call)
OPENAI_ANALYSIS_INPUT_PRICE_PER_1M = 1.25
OPENAI_ANALYSIS_OUTPUT_PRICE_PER_1M = 10.00

# Display labels / models for the analysis section of the cost report.
# Keep these model strings in sync with analysis_providers.ANALYSIS_MODELS.
ANALYSIS_PROVIDER_LABELS = {
    "claude": "Claude API",
    "gemini": "Gemini API",
    "openai": "OpenAI API",
}
ANALYSIS_PROVIDER_MODELS = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-3.5-flash",
    "openai": "gpt-5.1",
}

# ── Gemini Live pricing (per 1M tokens, USD) ─────────────────────────────────
# gemini-2.0-flash-live; audio input billed as tokens (~32 tokens/second at 16kHz)
GEMINI_AUDIO_INPUT_PRICE_PER_1M = 0.50   # audio tokens (multimodal input)
GEMINI_TEXT_OUTPUT_PRICE_PER_1M = 1.50   # text output tokens
GEMINI_AUDIO_SECONDS_TO_TOKENS = 32      # ~32 tokens per audio second

# ── OpenAI Realtime pricing (per 1M tokens, USD) ─────────────────────────────
# gpt-4o-realtime-preview
OPENAI_AUDIO_INPUT_PRICE_PER_1M = 100.00  # audio input tokens
OPENAI_AUDIO_OUTPUT_PRICE_PER_1M = 200.00  # audio output tokens
OPENAI_TEXT_INPUT_PRICE_PER_1M = 5.00
OPENAI_TEXT_OUTPUT_PRICE_PER_1M = 20.00
# Audio tokens: ~32 tokens/second at 16kHz PCM16
OPENAI_AUDIO_SECONDS_TO_TOKENS = 32
# Rough natural speech rate, used to estimate spoken-audio duration from the
# length of the transcribed text (~15 characters per second of speech).
SPEECH_CHARS_PER_SECOND = 15


def _estimate_openai_output_audio_tokens(output_chars: int) -> int:
    """Estimate spoken audio-output tokens from transcript length.

    The model's reply is billed as *audio* output tokens. We approximate the
    spoken duration from the transcript text, then convert seconds → tokens.
    """
    est_output_seconds = output_chars / SPEECH_CHARS_PER_SECOND
    return max(int(est_output_seconds * OPENAI_AUDIO_SECONDS_TO_TOKENS), 1)


@dataclass
class SessionCostReport:
    session_id: Optional[int] = None
    created_at: str = ""
    mode: str = ""
    case_name: str = ""
    voice_backend: str = ""
    duration_seconds: int = 0

    # Which provider ran the post-session analysis (claude/gemini/openai). The
    # token/cost fields below keep the historical ``claude_*`` names regardless
    # of provider so the DB schema does not need to change.
    analysis_provider: str = "claude"
    analysis_model: str = ""

    # Analysis (feedback) call
    claude_input_tokens: int = 0
    claude_output_tokens: int = 0
    claude_cached_input_tokens: int = 0

    # Voice backend
    voice_audio_seconds: int = 0
    voice_transcript_chars: int = 0
    voice_estimated_input_tokens: int = 0
    voice_estimated_output_tokens: int = 0

    # Computed costs (USD)
    claude_cost_usd: float = 0.0
    voice_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    notes: list[str] = field(default_factory=list)


def compute_claude_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Compute Claude API cost in USD. Cached tokens billed at 10% of input price."""
    non_cached = max(0, input_tokens - cached_tokens)
    cost = (non_cached * CLAUDE_INPUT_PRICE_PER_1M / 1_000_000
            + cached_tokens * CLAUDE_INPUT_PRICE_PER_1M * 0.1 / 1_000_000
            + output_tokens * CLAUDE_OUTPUT_PRICE_PER_1M / 1_000_000)
    return round(cost, 6)


def compute_analysis_cost(
    provider: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> float:
    """Compute the post-session analysis cost in USD for the chosen provider."""
    p = (provider or "claude").lower()
    if p == "gemini":
        cost = (input_tokens * GEMINI_ANALYSIS_INPUT_PRICE_PER_1M
                + output_tokens * GEMINI_ANALYSIS_OUTPUT_PRICE_PER_1M) / 1_000_000
        return round(cost, 6)
    if p == "openai":
        cost = (input_tokens * OPENAI_ANALYSIS_INPUT_PRICE_PER_1M
                + output_tokens * OPENAI_ANALYSIS_OUTPUT_PRICE_PER_1M) / 1_000_000
        return round(cost, 6)
    return compute_claude_cost(input_tokens, output_tokens, cached_tokens)


def compute_gemini_voice_cost(duration_seconds: int, output_chars: int) -> float:
    """Estimate Gemini Live cost from session duration and output transcript length."""
    input_tokens = duration_seconds * GEMINI_AUDIO_SECONDS_TO_TOKENS
    # Rough estimate: 1 token ≈ 4 chars for English text output
    output_tokens = max(output_chars // 4, 1)
    cost = (input_tokens * GEMINI_AUDIO_INPUT_PRICE_PER_1M / 1_000_000
            + output_tokens * GEMINI_TEXT_OUTPUT_PRICE_PER_1M / 1_000_000)
    return round(cost, 6)


def compute_openai_voice_cost(duration_seconds: int, output_chars: int) -> float:
    """Estimate OpenAI Realtime cost from session duration and output transcript length."""
    input_tokens = duration_seconds * OPENAI_AUDIO_SECONDS_TO_TOKENS
    output_tokens = _estimate_openai_output_audio_tokens(output_chars)
    cost = (input_tokens * OPENAI_AUDIO_INPUT_PRICE_PER_1M / 1_000_000
            + output_tokens * OPENAI_AUDIO_OUTPUT_PRICE_PER_1M / 1_000_000)
    return round(cost, 6)


def build_report_from_session(
    session: dict,
    claude_response_obj: Optional[object] = None,
    analysis_provider: str = "claude",
    analysis_usage: Optional[dict] = None,
) -> SessionCostReport:
    """
    Build a SessionCostReport from a DB session dict.

    analysis_provider: which LLM ran the feedback analysis (claude/gemini/openai).
    analysis_usage: normalized token dict {input_tokens, output_tokens, cached_tokens}
        from the provider call. Preferred source of exact counts.
    claude_response_obj: legacy path — a raw anthropic.Message object for exact
        Claude token counts (still supported for backward compatibility).
    """
    report = SessionCostReport(
        session_id=session.get("id"),
        created_at=session.get("created_at", ""),
        mode=session.get("mode", ""),
        case_name=session.get("case_name", ""),
        voice_backend=session.get("voice_backend", ""),
        duration_seconds=session.get("duration_seconds") or 0,
        analysis_provider=(analysis_provider or "claude").lower(),
        analysis_model=ANALYSIS_PROVIDER_MODELS.get((analysis_provider or "claude").lower(), ""),
    )

    # ── Analysis token counts ──────────────────────────────────────────────
    if analysis_usage is not None:
        # Preferred: normalized usage dict from the provider call.
        report.claude_input_tokens = analysis_usage.get("input_tokens", 0) or 0
        report.claude_output_tokens = analysis_usage.get("output_tokens", 0) or 0
        report.claude_cached_input_tokens = analysis_usage.get("cached_tokens", 0) or 0
    elif claude_response_obj is not None:
        # Legacy: exact counts from a raw anthropic.Message object.
        usage = getattr(claude_response_obj, "usage", None)
        if usage:
            report.claude_input_tokens = getattr(usage, "input_tokens", 0)
            report.claude_output_tokens = getattr(usage, "output_tokens", 0)
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            report.claude_cached_input_tokens = cache_read
    else:
        # Estimate from stored raw prompt (approximate: 1 token ≈ 4 chars)
        from app.analysis.prompt_builder import build_analysis_prompt
        transcript_str = session.get("raw_transcript", "[]")
        case_str = session.get("raw_case_json", "{}")
        eval_str = session.get("raw_eval_json") or "{}"
        try:
            transcript = json.loads(transcript_str)
            case_data = json.loads(case_str)
            eval_data = json.loads(eval_str)
            prompt = build_analysis_prompt(transcript, case_data, eval_data)
            report.claude_input_tokens = len(prompt) // 4
        except Exception:
            report.claude_input_tokens = 0

        raw_resp = session.get("raw_claude_response")
        if raw_resp:
            report.claude_output_tokens = len(raw_resp) // 4
        report.notes.append("Claude token counts are estimated (API response object not available).")

    report.claude_cost_usd = compute_analysis_cost(
        report.analysis_provider,
        report.claude_input_tokens,
        report.claude_output_tokens,
        report.claude_cached_input_tokens,
    )

    # ── Voice backend costs ────────────────────────────────────────────────
    transcript_str = session.get("raw_transcript", "[]")
    try:
        turns = json.loads(transcript_str)
        ai_turns = [t for t in turns if t.get("role") in ("patient", "interviewer")]
        report.voice_transcript_chars = sum(len(t.get("text", "")) for t in ai_turns)
    except Exception:
        report.voice_transcript_chars = 0

    report.voice_audio_seconds = report.duration_seconds
    backend = report.voice_backend.lower()

    if backend == "gemini":
        report.voice_estimated_input_tokens = report.duration_seconds * GEMINI_AUDIO_SECONDS_TO_TOKENS
        report.voice_estimated_output_tokens = max(report.voice_transcript_chars // 4, 1)
        report.voice_cost_usd = compute_gemini_voice_cost(
            report.duration_seconds, report.voice_transcript_chars
        )
    elif backend == "openai":
        report.voice_estimated_input_tokens = report.duration_seconds * OPENAI_AUDIO_SECONDS_TO_TOKENS
        report.voice_estimated_output_tokens = _estimate_openai_output_audio_tokens(
            report.voice_transcript_chars
        )
        report.voice_cost_usd = compute_openai_voice_cost(
            report.duration_seconds, report.voice_transcript_chars
        )
    else:
        report.notes.append(f"Voice backend '{backend}' (mock) — no cost.")

    report.total_cost_usd = round(report.claude_cost_usd + report.voice_cost_usd, 6)
    return report


def format_report_text(report: SessionCostReport) -> str:
    """Render a SessionCostReport as a human-readable text block."""
    lines = [
        "=" * 60,
        "  MedVoiceTrainer — Session API Cost Report",
        "=" * 60,
        f"  Generated : {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Session ID: {report.session_id}",
        f"  Date      : {report.created_at[:19]}",
        f"  Mode      : {report.mode.capitalize()}",
        f"  Case      : {report.case_name}",
        f"  Backend   : {report.voice_backend}",
        f"  Duration  : {report.duration_seconds // 60}m {report.duration_seconds % 60}s",
        "",
        f"── {ANALYSIS_PROVIDER_LABELS.get(report.analysis_provider, 'Claude API')} (Post-Session Analysis) ──────────────────",
        f"  Model            : {report.analysis_model or ANALYSIS_PROVIDER_MODELS.get(report.analysis_provider, 'claude-sonnet-4-6')}",
        f"  Input tokens     : {report.claude_input_tokens:,}",
        f"  Cached tokens    : {report.claude_cached_input_tokens:,}",
        f"  Output tokens    : {report.claude_output_tokens:,}",
        f"  Cost             : ${report.claude_cost_usd:.6f}",
        "",
    ]

    backend = report.voice_backend.lower()
    if backend == "gemini":
        lines += [
            "── Gemini Live (Voice Session) ─────────────────────────",
            f"  Model            : Gemini Live (flash, native audio)",
            f"  Audio seconds    : {report.voice_audio_seconds}s",
            f"  Est. input tokens: {report.voice_estimated_input_tokens:,}",
            f"  Est. output chars: {report.voice_transcript_chars:,}",
            f"  Cost (estimated) : ${report.voice_cost_usd:.6f}",
            "",
        ]
    elif backend == "openai":
        lines += [
            "── OpenAI Realtime (Voice Session) ─────────────────────",
            f"  Model            : gpt-4o-realtime-preview",
            f"  Audio seconds    : {report.voice_audio_seconds}s",
            f"  Est. input tokens: {report.voice_estimated_input_tokens:,}",
            f"  Est. output tokens: {report.voice_estimated_output_tokens:,}",
            f"  Cost (estimated) : ${report.voice_cost_usd:.6f}",
            "",
        ]
    else:
        lines += [
            f"── Voice Backend: {report.voice_backend} (no cost) ────────────",
            "",
        ]

    lines += [
        "── Total ────────────────────────────────────────────────",
        f"  TOTAL COST (USD) : ${report.total_cost_usd:.6f}",
        "=" * 60,
    ]

    if report.notes:
        lines.append("\nNotes:")
        for note in report.notes:
            lines.append(f"  * {note}")

    return "\n".join(lines)


def save_cost_report(report: SessionCostReport, output_dir: str) -> str:
    """Save the cost report as a .txt file and return the path."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    filename = f"cost_report_{report.session_id or ts}_{ts}.txt"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(format_report_text(report))
    return path
