import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

import config
from app.ui.session_base import SessionBase
from app.analysis.prompt_builder import build_interview_prompt


def _load_interview_scenarios() -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {"behavioral": [], "clinical": [], "img_specific": [], "basic_science": []}
    if not os.path.isdir(config.INTERVIEW_BANKS_DIR):
        return cats
    for fname in os.listdir(config.INTERVIEW_BANKS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(config.INTERVIEW_BANKS_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            for scenario in data.get("scenarios", []):
                cat = scenario.get("category", "behavioral")
                if cat in cats:
                    cats[cat].append(scenario)
                else:
                    cats.setdefault(cat, []).append(scenario)
        except Exception:
            pass
    return cats


def _load_eval(template_name: str) -> Optional[dict]:
    path = os.path.join(config.EVAL_DIR, f"{template_name}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


CATEGORY_LABELS = {
    "behavioral": "Behavioral",
    "clinical": "Clinical",
    "img_specific": "IMG-Specific",
    "basic_science": "Basic Science Viva",
}


class InterviewTab(SessionBase):
    def __init__(self, parent: ttk.Notebook, dev_mode: bool = False):
        self.frame = tk.Frame(parent)
        super().__init__(self.frame, dev_mode=dev_mode)
        self.mode = "interview"
        self._all_scenarios = _load_interview_scenarios()
        self._build_ui()

    def _build_ui(self) -> None:
        # Selector row
        selector = tk.Frame(self.frame, bg="#f9fafb", relief=tk.RIDGE, bd=1)
        selector.pack(fill=tk.X, padx=6, pady=4)

        tk.Label(selector, text="Category:", bg="#f9fafb", font=("Segoe UI", 10)).grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self._cat_var = tk.StringVar()
        self._cat_cb = ttk.Combobox(
            selector, textvariable=self._cat_var,
            values=[CATEGORY_LABELS[k] for k in ["behavioral", "clinical", "img_specific", "basic_science"]],
            width=16, state="readonly",
        )
        self._cat_cb.grid(row=0, column=1, padx=4, pady=6)
        self._cat_cb.bind("<<ComboboxSelected>>", self._on_category_change)

        tk.Label(selector, text="Scenario:", bg="#f9fafb", font=("Segoe UI", 10)).grid(row=0, column=2, padx=8, pady=6, sticky="w")
        self._scenario_var = tk.StringVar()
        self._scenario_cb = ttk.Combobox(selector, textvariable=self._scenario_var, width=40, state="readonly")
        selector.columnconfigure(3, weight=1)
        self._scenario_cb.grid(row=0, column=3, padx=4, pady=6, sticky="ew")
        self._scenario_cb.bind("<<ComboboxSelected>>", self._on_scenario_change)

        # Info bar
        self._info_var = tk.StringVar(value="")
        info_bar = tk.Label(selector, textvariable=self._info_var, bg="#f9fafb",
                            font=("Segoe UI", 9, "italic"), foreground="#4b5563")
        info_bar.grid(row=1, column=0, columnspan=4, padx=8, pady=(0, 6), sticky="w")

        self._cat_cb.current(0)
        self._on_category_change()

        # Session area
        session_container = tk.Frame(self.frame)
        session_container.pack(fill=tk.BOTH, expand=True)
        self._build_session_ui(session_container)

    def _on_category_change(self, event=None) -> None:
        cat_label = self._cat_var.get()
        cat_key = {v: k for k, v in CATEGORY_LABELS.items()}.get(cat_label, "behavioral")
        scenarios = self._all_scenarios.get(cat_key, [])
        labels = [f"{s.get('id', '?')} — {s.get('opening_question', '')[:50]}" for s in scenarios]
        self._scenario_cb["values"] = labels
        self._scenario_cb_items = scenarios
        if labels:
            self._scenario_cb.current(0)
            self._on_scenario_change()
        else:
            self.current_case = None
            self.current_eval = None
            self._info_var.set("No scenarios found.")

    def _on_scenario_change(self, event=None) -> None:
        idx = self._scenario_cb.current()
        if idx < 0 or not hasattr(self, "_scenario_cb_items"):
            return
        scenario = self._scenario_cb_items[idx]
        self.current_case = scenario
        eval_tpl = scenario.get("eval_template", "residency_interview")
        self.current_eval = _load_eval(eval_tpl)
        self._info_var.set(
            f"PD: {scenario.get('pd_name', '?')}  ·  Program: {scenario.get('program', '?')}"
        )

    def _build_system_prompt(self) -> str:
        return build_interview_prompt(self.current_case)
