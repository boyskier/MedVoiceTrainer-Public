import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

import config
from app.ui.session_base import SessionBase
from app.analysis.prompt_builder import assign_complexity_modifier, build_patient_prompt
from app.analysis.coverage import (
    CoverageTracker, build_guided_script, supports_history_coverage,
)


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
        self._tracker = CoverageTracker()
        self._ob_stage = 0          # how many answer-sheet sections are revealed
        self._gs_steps: list[dict] = []
        self._gs_index = 0
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

        # Beginner scaffolds: open-book answer sheet + guided script
        aids_row = tk.Frame(selector, bg="#f9fafb")
        aids_row.grid(row=1, column=0, columnspan=7, sticky="w", padx=8, pady=(0, 6))
        self._open_book_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            aids_row, text="📖 Open-book — show the case answer sheet while you talk",
            variable=self._open_book_var, command=self._refresh_aid_panels,
        ).pack(side=tk.LEFT, padx=(0, 18))
        self._guided_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            aids_row, text="🧭 Guided script — read model questions step by step",
            variable=self._guided_var, command=self._refresh_aid_panels,
        ).pack(side=tk.LEFT)

        # Session area
        session_container = tk.Frame(self.frame)
        session_container.pack(fill=tk.BOTH, expand=True)
        self._build_session_ui(session_container)
        self._build_open_book_panel(session_container)
        self._build_guided_panel(session_container)

        if self._system_cb["values"]:
            self._system_cb.current(0)
            self._on_system_change()

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
        self._ob_stage = 0
        self._tracker.reset()
        self._refresh_aid_panels()

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
        self._refresh_aid_panels()
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

    # ── Open-book answer-sheet panel ──────────────────────────────────────────

    def _build_open_book_panel(self, container: tk.Frame) -> None:
        self._ob_frame = tk.Frame(container, bg="#fff7ed", relief=tk.RIDGE, bd=1)
        header = tk.Frame(self._ob_frame, bg="#fff7ed")
        header.pack(fill=tk.X)
        tk.Label(header, text="📖 Answer Sheet — what this patient really has",
                 font=("Segoe UI", 9, "bold"), bg="#fff7ed", anchor="w").pack(
            side=tk.LEFT, padx=8, pady=2)
        self._ob_reveal_btn = ttk.Button(header, text="🔓 Reveal next section",
                                         command=self._reveal_next_section)
        self._ob_reveal_btn.pack(side=tk.RIGHT, padx=8, pady=2)

        self._ob_text = tk.Text(
            self._ob_frame, wrap=tk.WORD, height=10, font=("Segoe UI", 9),
            bg="#ffffff", relief=tk.FLAT, padx=8, pady=6, cursor="arrow",
        )
        sb = ttk.Scrollbar(self._ob_frame, command=self._ob_text.yview)
        self._ob_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._ob_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self._ob_text.tag_configure("head", font=("Segoe UI", 9, "bold"), foreground="#b45309", spacing1=6)
        self._ob_text.tag_configure("body", foreground="#111827", lmargin1=12, lmargin2=12)
        self._ob_text.tag_configure("done", foreground="#16a34a", lmargin1=12, lmargin2=12)
        self._ob_text.tag_configure("todo", foreground="#6b7280", lmargin1=12, lmargin2=12)
        self._ob_text.tag_configure("hint", font=("Segoe UI", 8, "italic"), foreground="#6b7280", spacing1=4)

    def _ob_sections(self, case: dict) -> list[tuple[str, str]]:
        """The staged-reveal sections present in this case, in reveal order."""
        ice = "\n".join(
            f"{label}: {case.get(key)}" for key, label in
            [("ideas", "Ideas"), ("concerns", "Concerns"), ("expectations", "Expectations")]
            if case.get(key)
        )
        pmh = "\n".join(
            f"{label}: {case.get(key)}" for key, label in
            [("pmh", "PMH"), ("medications", "Medications")] if case.get(key)
        )
        soap = case.get("reference_soap") or {}
        model = "\n".join(f"{k.capitalize()}: {v}" for k, v in soap.items() if v)
        sections = [
            ("History of presenting illness (HPI)", case.get("hpi_details", "")),
            ("Patient's ICE — what they think / fear / want", ice),
            ("Past medical history & medications", pmh),
            ("Social history", case.get("social_hx", "")),
            ("Model note (reference SOAP)", model),
        ]
        return [(t, b) for t, b in sections if b]

    def _reveal_next_section(self) -> None:
        case = self.current_case or {}
        if self._ob_stage < len(self._ob_sections(case)):
            self._ob_stage += 1
            aids = case.get("practice_aids")
            if isinstance(aids, dict):
                aids["sections_revealed"] = self._ob_stage
            self._render_open_book()

    def _render_open_book(self) -> None:
        case = self.current_case or {}
        txt = self._ob_text
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)
        who = " · ".join(str(x) for x in [
            case.get("patient_name"), case.get("age") and f"{case['age']} y",
            case.get("gender")] if x)
        txt.insert(tk.END, f"Patient: {who or 'unknown'}\n", "head")
        txt.insert(tk.END, f"Chief complaint: {case.get('chief_complaint', '—')}\n", "body")

        txt.insert(tk.END, "What to ask (checks itself off as you ask):\n", "head")
        for d in self._tracker.domains:
            if d["key"] in self._tracker.covered:
                txt.insert(tk.END, f"☑ {d.get('label', d['key'])}\n", "done")
            else:
                txt.insert(tk.END, f"☐ {d.get('label', d['key'])}\n", "todo")

        sections = self._ob_sections(case)
        for i, (title, body) in enumerate(sections):
            if i < self._ob_stage:
                txt.insert(tk.END, f"{title}\n", "head")
                txt.insert(tk.END, f"{body}\n", "body")
        remaining = len(sections) - self._ob_stage
        if remaining > 0:
            nxt = sections[self._ob_stage][0]
            txt.insert(tk.END,
                       f"\n🔒 {remaining} section(s) hidden — next: {nxt}. "
                       "Try asking first; reveal only when you need it.\n", "hint")
        txt.config(state=tk.DISABLED)

    # ── Guided-script panel ───────────────────────────────────────────────────

    def _build_guided_panel(self, container: tk.Frame) -> None:
        self._gs_frame = tk.Frame(container, bg="#eff6ff", relief=tk.RIDGE, bd=1)
        header = tk.Frame(self._gs_frame, bg="#eff6ff")
        header.pack(fill=tk.X)
        tk.Label(header, text="🧭 Guided Script — read the ▶ line aloud, then listen",
                 font=("Segoe UI", 9, "bold"), bg="#eff6ff", anchor="w").pack(
            side=tk.LEFT, padx=8, pady=2)
        ttk.Button(header, text="Skip step ▸", command=self._gs_skip).pack(
            side=tk.RIGHT, padx=8, pady=2)

        self._gs_text = tk.Text(
            self._gs_frame, wrap=tk.WORD, height=8, font=("Segoe UI", 10),
            bg="#ffffff", relief=tk.FLAT, padx=8, pady=6, cursor="arrow",
        )
        sb = ttk.Scrollbar(self._gs_frame, command=self._gs_text.yview)
        self._gs_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._gs_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self._gs_text.tag_configure("done", foreground="#9ca3af", lmargin1=8, lmargin2=24, overstrike=True)
        self._gs_text.tag_configure("current", font=("Segoe UI", 11, "bold"), foreground="#1d4ed8",
                                    lmargin1=8, lmargin2=24, spacing1=4, spacing3=4)
        self._gs_text.tag_configure("pending", foreground="#374151", lmargin1=8, lmargin2=24)
        self._gs_text.tag_configure("label", font=("Segoe UI", 8), foreground="#6b7280", lmargin1=24)

    def _gs_skip(self) -> None:
        if self._gs_index < len(self._gs_steps):
            self._gs_index += 1
            self._render_guided()

    def _render_guided(self) -> None:
        txt = self._gs_text
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)
        for i, step in enumerate(self._gs_steps):
            if i < self._gs_index:
                txt.insert(tk.END, f"✔ {step['question']}\n", "done")
            elif i == self._gs_index:
                txt.insert(tk.END, f"▶ {step['question']}\n", "current")
                txt.insert(tk.END, f"   ({step['label']})\n", "label")
            else:
                txt.insert(tk.END, f"· {step['question']}\n", "pending")
        if self._gs_index >= len(self._gs_steps):
            txt.insert(tk.END, "\n🎉 Script finished — summarize and close the consultation.\n", "current")
        else:
            # Keep the active step in view.
            txt.see(f"{self._gs_index + 1}.0")
        txt.config(state=tk.DISABLED)

    # ── Showing/hiding the scaffold panels ────────────────────────────────────

    def _aids_supported(self) -> bool:
        return supports_history_coverage(self.current_case)

    def _refresh_aid_panels(self) -> None:
        if not hasattr(self, "_ob_frame"):
            return
        supported = self._aids_supported()
        if self._open_book_var.get() and supported:
            self._render_open_book()
            if not self._ob_frame.winfo_ismapped():
                self._ob_frame.pack(fill=tk.X, padx=6, pady=(0, 4),
                                    before=self._transcript_container)
        else:
            self._ob_frame.pack_forget()

        if self._guided_var.get() and supported:
            self._gs_steps = build_guided_script(self.current_case or {})
            self._gs_index = 0
            self._render_guided()
            if not self._gs_frame.winfo_ismapped():
                self._gs_frame.pack(fill=tk.BOTH, padx=6, pady=(0, 4),
                                    before=self._transcript_container)
        else:
            self._gs_frame.pack_forget()

        if (self._open_book_var.get() or self._guided_var.get()) and not supported:
            from tkinter import messagebox
            messagebox.showinfo(
                "Practice aids",
                "Open-book and Guided script work with standard patient cases.\n"
                "Skill drills and personalised reviews bring their own scaffolding "
                "(see the Phrase Helper).",
            )
            self._open_book_var.set(False)
            self._guided_var.set(False)

    # ── Session hooks ─────────────────────────────────────────────────────────

    def _add_extra_controls(self, ctrl_frame: tk.Frame) -> None:
        self._stuck_btn = ttk.Button(ctrl_frame, text="💡 I'm stuck",
                                     command=self._on_stuck, state=tk.DISABLED)
        self._stuck_btn.pack(side=tk.LEFT, padx=4, pady=6)

    def _on_stuck(self) -> None:
        """Suggest the next uncovered history domain — rule-based, no API call."""
        if not self._running or not self._aids_supported():
            return
        domain = self._tracker.next_hint()
        if domain is None:
            self._append_system_message(
                "💡 You've touched every key area — summarize what you heard and close."
            )
            return
        question = domain.get("questions", [""])[0]
        self._append_system_message(
            f'💡 Try asking ({domain.get("label", "")}): “{question}”'
        )
        aids = (self.current_case or {}).get("practice_aids")
        if isinstance(aids, dict):
            aids["hints_used"] = aids.get("hints_used", 0) + 1

    def _on_user_turn(self, text: str) -> None:
        if not self._running or not self._aids_supported():
            return
        newly = self._tracker.update(text)
        if not newly:
            return
        if self._open_book_var.get():
            self._render_open_book()
        if self._guided_var.get() and self._gs_index < len(self._gs_steps):
            # Auto-advance past every consecutive step the student has now covered.
            while (self._gs_index < len(self._gs_steps)
                   and self._gs_steps[self._gs_index]["domain"] in self._tracker.covered):
                self._gs_index += 1
            self._render_guided()

    def _on_stop(self) -> None:
        super()._on_stop()
        if hasattr(self, "_stuck_btn"):
            self._stuck_btn.config(state=tk.DISABLED)

    def _build_system_prompt(self) -> str:
        # Roll the per-session complexity modifier on a copy of the case so the
        # cached case list is never mutated and the session row records exactly
        # what the live patient was instructed to act out.
        self.current_case = assign_complexity_modifier(self.current_case)

        open_book = self._open_book_var.get() and self._aids_supported()
        guided = self._guided_var.get() and self._aids_supported()
        if open_book or guided:
            # Beginner scaffolds: no surprise behavioral twist, patient slows
            # down (coaching mode), and the analysis is told aids were in play.
            self.current_case.pop("active_complexity_modifier", None)
            self.current_case["coaching_mode"] = True
            self.current_case["practice_aids"] = {
                "open_book": open_book,
                "guided_script": guided,
                "sections_revealed": 0,
                "hints_used": 0,
            }

        # Fresh per-session scaffold state.
        self._tracker.reset()
        self._ob_stage = 0
        self._refresh_aid_panels()
        if self._aids_supported() and hasattr(self, "_stuck_btn"):
            self._stuck_btn.config(state=tk.NORMAL)

        return build_patient_prompt(self.current_case)
