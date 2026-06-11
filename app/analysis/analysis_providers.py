"""Pluggable post-session analysis (feedback) providers.

The post-session analysis — scoring, corrections, Anki cards, SOAP comparison —
is a single text-in / JSON-out LLM call. Unlike the real-time voice step it has
no latency or streaming constraints, so it can run on whichever provider the
user already has an API key for. The user picks the backend in Preferences
(the ``feedback_backend`` setting); this module hides the per-SDK differences
behind one :func:`call_analysis` entry point.

Each backend returns ``(raw_text, usage)`` where ``usage`` is a normalized dict::

    {"input_tokens": int, "output_tokens": int, "cached_tokens": int}

so the cost tracker never needs provider-specific branches at the call site.
"""
import os

ANALYSIS_SYSTEM_PROMPT = (
    "You are a precise medical education evaluator. "
    "Always return valid JSON exactly matching the requested schema."
)

# Text models used for the analysis call. These are NOT the real-time voice
# models used during the live session. Pinned to current (2026-Q2) models;
# bump these as newer releases ship — they are the only place model IDs live.
ANALYSIS_MODELS = {
    "claude": "claude-sonnet-4-6",     # strong, cost-appropriate JSON evaluator
    "gemini": "gemini-3.5-flash",      # latest GA Flash — fast, cheap, JSON-native
    "openai": "gpt-5.1",               # flagship; reasoning model (see _call_openai)
}

# Output token ceilings, per provider. OpenAI/Gemini reasoning models spend
# hidden reasoning tokens against this budget, so they need more headroom than
# Claude (whose analysis call runs without extended thinking).
CLAUDE_MAX_TOKENS = 4096
GEMINI_MAX_OUTPUT_TOKENS = 8192
OPENAI_MAX_COMPLETION_TOKENS = 8192

# GPT-5.x is a reasoning model. A formatting/scoring task does not need deep
# reasoning, so keep effort low to cut latency/cost and leave the token budget
# above for the JSON itself rather than internal reasoning.
OPENAI_REASONING_EFFORT = "low"


def call_analysis(backend: str, prompt: str) -> tuple[str, dict]:
    """Dispatch the analysis call to the selected backend.

    Returns ``(raw_text, usage)``. Raises ``ValueError`` for a missing API key
    or missing SDK so the UI can show an actionable message; other exceptions
    (network, rate limit) propagate as-is.
    """
    if backend == "gemini":
        return _call_gemini(prompt)
    if backend == "openai":
        return _call_openai(prompt)
    return _call_claude(prompt)


def _empty_usage() -> dict:
    return {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}


def _call_claude(prompt: str) -> tuple[str, dict]:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it to .env or Preferences.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=ANALYSIS_MODELS["claude"],
        max_tokens=CLAUDE_MAX_TOKENS,
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = message.content[0].text.strip()
    usage = _empty_usage()
    u = getattr(message, "usage", None)
    if u:
        usage["input_tokens"] = getattr(u, "input_tokens", 0) or 0
        usage["output_tokens"] = getattr(u, "output_tokens", 0) or 0
        usage["cached_tokens"] = getattr(u, "cache_read_input_tokens", 0) or 0
    return raw_text, usage


def _call_gemini(prompt: str) -> tuple[str, dict]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ValueError("google-genai package not installed. Run: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set. Add it to .env or Preferences.")

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=ANALYSIS_MODELS["gemini"],
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=ANALYSIS_SYSTEM_PROMPT,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            # Force a pure-JSON response so parsing never trips over prose.
            response_mime_type="application/json",
        ),
    )

    # resp.text can raise (not just return None) when the candidate was blocked
    # or contains no text parts; treat any such case as an empty response so the
    # caller surfaces a clean "invalid JSON" error rather than an opaque crash.
    try:
        raw_text = (resp.text or "").strip()
    except Exception:
        raw_text = ""
    usage = _empty_usage()
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        usage["input_tokens"] = getattr(meta, "prompt_token_count", 0) or 0
        usage["output_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
        usage["cached_tokens"] = getattr(meta, "cached_content_token_count", 0) or 0
    return raw_text, usage


def _call_openai(prompt: str) -> tuple[str, dict]:
    try:
        import openai
    except ImportError:
        raise ValueError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set. Add it to .env or Preferences.")

    client = openai.OpenAI(api_key=api_key)
    # GPT-5.x is a reasoning model: it rejects `max_tokens` (use
    # `max_completion_tokens`) and `temperature`, and accepts `reasoning_effort`.
    resp = client.chat.completions.create(
        model=ANALYSIS_MODELS["openai"],
        max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
        reasoning_effort=OPENAI_REASONING_EFFORT,
        # JSON mode requires the word "json" in the prompt — the schema
        # instruction supplies it.
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw_text = (resp.choices[0].message.content or "").strip()
    usage = _empty_usage()
    u = getattr(resp, "usage", None)
    if u:
        usage["input_tokens"] = getattr(u, "prompt_tokens", 0) or 0
        usage["output_tokens"] = getattr(u, "completion_tokens", 0) or 0
    return raw_text, usage
