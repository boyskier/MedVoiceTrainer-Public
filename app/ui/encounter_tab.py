import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

import config
from app.ui.session_base import SessionBase
from app.analysis.prompt_builder import assign_complexity_modifier, build_patient_prompt


def _load_cases() -> dict[str, list[dict]]:
    """Returns {system: [case_dict, ...]}"""
    cases: dict[str, list[dict]] = {}
    for system in config.CASE_SYSTEMS:
        system_dir = os.path.join(config.CASES_DIR, system)
        if not os.path.isdir(system_dir):
            continue
        case_list = []
        for fname in sorted(os.listdir(system_dir)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(system_dir, fname), encoding="utf-8") as f:
                        case_list.append(json.load(f))
                except Exception:
                    pass
        if case_list:
            cases[system] = case_list
    return cases


def _load_eval(template_name: str) -> Optional[dict]:
    path = os.path.join(config.EVAL_DIR, f"{template_name}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


DIFFICULTIES = ["all", "beginner", "intermediate", "advanced"]


class EncounterTab(SessionBase):
    def __init__(self, parent: ttk.Notebook, dev_mode: bool = False):
        self.frame = tk.Frame(parent)
        super().__init__(self.frame, dev_mode=dev_mode)
        self.mode = "encounter"
        self._all_cases = _load_cases()
        self._build_ui()

    def _build_ui(self) -> None:
        # Selector row
        selector = tk.Frame(self.frame, bg="#f9fafb", relief=tk.RIDGE, bd=1)
        selector.pack(fill=tk.X, padx=6, pady=4)

        tk.Label(selector, text="System:", bg="#f9fafb", font=("Segoe UI", 10)).grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self._system_var = tk.StringVar()
        self._system_cb = ttk.Combobox(selector, textvariable=self._system_var, width=16, state="readonly")
        self._system_cb["values"] = list(self._all_cases.keys())
        self._system_cb.grid(row=0, column=1, padx=4, pady=6)
        self._system_cb.bind("<<ComboboxSelected>>", self._on_system_change)

        tk.Label(selector, text="Case:", bg="#f9fafb", font=("Segoe UI", 10)).grid(row=0, column=2, padx=8, pady=6, sticky="w")
        self._case_var = tk.StringVar()
        self._case_cb = ttk.Combobox(selector, textvariable=self._case_var, width=30, state="readonly")
        selector.columnconfigure(3, weight=1)
        self._case_cb.grid(row=0, column=3, padx=4, pady=6, sticky="ew")
        self._case_cb.bind("<<ComboboxSelected>>", self._on_case_change)

        tk.Label(selector, text="Difficulty:", bg="#f9fafb", font=("Segoe UI", 10)).grid(row=0, column=4, padx=8, pady=6, sticky="w")
        self._diff_var = tk.StringVar(value="all")
        self._diff_cb = ttk.Combobox(selector, textvariable=self._diff_var, values=DIFFICULTIES, width=12, state="readonly")
        self._diff_cb.grid(row=0, column=5, padx=4, pady=6)
        self._diff_cb.bind("<<ComboboxSelected>>", self._on_difficulty_change)

        # Personalised review launcher (uses the user's own past corrections)
        self._review_btn = ttk.Button(
            selector, text="🎯 My Mistakes", command=self._start_review
        )
        self._review_btn.grid(row=0, column=6, padx=(16, 8), pady=6)

        if self._system_cb["values"]:
            self._system_cb.current(0)
            self._on_system_change()

        # Session area
        session_container = tk.Frame(self.frame)
        session_container.pack(fill=tk.BOTH, expand=True)
        self._build_session_ui(session_container)

        # Now that the session UI (incl. Phrase Helper) exists, reflect the
        # initially-selected case (the first _on_case_change ran before build).
        self.refresh_phrase_helper()

    def _on_system_change(self, event=None) -> None:
        system = self._system_var.get()
        cases = self._all_cases.get(system, [])
        self._diff_var.set("all")
        self._populate_case_combo(cases)

    def _on_difficulty_change(self, event=None) -> None:
        system = self._system_var.get()
        diff = self._diff_var.get()
        cases = self._all_cases.get(system, [])
        if diff != "all":
            cases = [c for c in cases if c.get("difficulty") == diff]
        self._populate_case_combo(cases)

    def _populate_case_combo(self, cases: list[dict]) -> None:
        labels = [
            f"{c.get('id', '?')} — {c.get('chief_complaint') or c.get('title') or 'unknown complaint'}"
            for c in cases
        ]
        self._case_cb["values"] = labels
        self._case_cb_cases = cases
        if labels:
            self._case_cb.current(0)
            self._on_case_change()
        else:
            self._case_var.set("")
            self.current_case = None
            self.current_eval = None

    def _on_case_change(self, event=None) -> None:
        idx = self._case_cb.current()
        if idx < 0 or not hasattr(self, "_case_cb_cases"):
            return
        self.current_case = self._case_cb_cases[idx]
        eval_template = self.current_case.get("eval_template", "history_taking")
        self.current_eval = _load_eval(eval_template)
        self.refresh_phrase_helper()

    def _start_review(self) -> None:
        """Load a personalised 'Practice My Mistakes' session from past corrections."""
        from tkinter import messagebox
        from app.analysis import review_builder

        targets = review_builder.prepare_targets()
        if len(targets) < review_builder.MIN_TARGETS:
            messagebox.showinfo(
                "Practice My Mistakes",
                "Not enough data yet.\n\nFinish a few practice sessions first so I can "
                "collect the language corrections to review "
                f"(need at least {review_builder.MIN_TARGETS}).",
            )
            return

        self.current_case = review_builder.build_review_case(targets)
        self.current_eval = review_builder.build_review_eval(targets)
        self.refresh_phrase_helper()
        self._append_system_message(
            f"Personalised review loaded with {len(targets)} target phrase(s) from your "
            "past sessions. The Phrase Helper shows them. Press ● Start when ready."
        )
        messagebox.showinfo(
            "Practice My Mistakes",
            f"Loaded {len(targets)} of your past corrections to practise out loud.\n\n"
            "The coach will set up situations where you produce the improved phrase.\n"
            "Press ● Start when you're ready.",
        )

    def _build_system_prompt(self) -> str:
        # Roll the per-session complexity modifier on a copy of the case so the
        # cached case list is never mutated and the session row records exactly
        # what the live patient was instructed to act out.
        self.current_case = assign_complexity_modifier(self.current_case)
        return build_patient_prompt(self.current_case)
