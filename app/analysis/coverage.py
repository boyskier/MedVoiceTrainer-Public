"""
Rule-based history-coverage tracking — no API calls.

Drives three beginner scaffolds in the encounter tab:
- the open-book panel's live "what to ask" checklist,
- the "I'm stuck" hint button (suggests the next uncovered domain's question),
- the guided-script fallback when a case ships no script of its own.

Matching is deliberately simple: lowercase substring keywords against the
student's own transcript turns. False negatives are harmless (the student just
sees an unchecked item they actually covered); false positives are rare because
the keywords are full phrases.
"""
from __future__ import annotations

import json

import config


def supports_history_coverage(case: dict | None) -> bool:
    """History domains only make sense for standard patient encounters, not
    free-form skill drills / handovers / personalised review personas."""
    return bool(case) and not case.get("persona_override")


def load_domains() -> list[dict]:
    try:
        with open(config.HISTORY_DOMAINS_PATH, encoding="utf-8") as f:
            return json.load(f).get("domains", [])
    except Exception:
        return []


class CoverageTracker:
    """Tracks which history domains the student's turns have touched."""

    def __init__(self, domains: list[dict] | None = None):
        self.domains = domains if domains is not None else load_domains()
        self.covered: set[str] = set()
        self._suggested: set[str] = set()

    def reset(self) -> None:
        self.covered.clear()
        self._suggested.clear()

    def update(self, user_text: str) -> set[str]:
        """Mark domains matched by this student turn; returns newly covered keys."""
        text = user_text.lower()
        new: set[str] = set()
        for d in self.domains:
            key = d.get("key", "")
            if key in self.covered:
                continue
            if any(kw in text for kw in d.get("keywords", [])):
                self.covered.add(key)
                new.add(key)
        return new

    def next_hint(self) -> dict | None:
        """First uncovered domain not already suggested — for the stuck button.
        Cycles back to uncovered-but-suggested domains once all have been shown."""
        uncovered = [d for d in self.domains if d.get("key") not in self.covered]
        if not uncovered:
            return None
        for d in uncovered:
            if d.get("key") not in self._suggested:
                self._suggested.add(d["key"])
                return d
        self._suggested.clear()
        self._suggested.add(uncovered[0]["key"])
        return uncovered[0]


def build_guided_script(case: dict) -> list[dict]:
    """Ordered list of {domain, label, question} steps for guided-script mode.

    A case may ship its own ``guided_script`` (list of strings or of
    {question, domain} dicts); otherwise one model question per generic
    history domain is used.
    """
    custom = case.get("guided_script")
    if custom:
        steps = []
        for i, entry in enumerate(custom):
            if isinstance(entry, str):
                steps.append({"domain": f"step_{i}", "label": f"Step {i + 1}", "question": entry})
            else:
                steps.append({
                    "domain": entry.get("domain", f"step_{i}"),
                    "label": entry.get("label", f"Step {i + 1}"),
                    "question": entry.get("question", ""),
                })
        return steps
    return [
        {"domain": d["key"], "label": d.get("label", d["key"]), "question": d["questions"][0]}
        for d in load_domains() if d.get("questions")
    ]
