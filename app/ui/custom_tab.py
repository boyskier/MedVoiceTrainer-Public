import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

import config
from app.ui.session_base import SessionBase
from app.analysis.prompt_builder import build_custom_prompt


def _list_eval_templates() -> list[str]:
    templates = []
    if os.path.isdir(config.EVAL_DIR):
        for fname in sorted(os.listdir(config.EVAL_DIR)):
            if fname.endswith(".json"):
                templates.append(fname[:-5])
    return templates


def _load_eval(template_name: str) -> Optional[dict]:
    path = os.path.join(config.EVAL_DIR, f"{template_name}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


class CustomTab(SessionBase):
    def __init__(self, parent: ttk.Notebook, dev_mode: bool = False):
        self.frame = tk.Frame(parent)
        super().__init__(self.frame, dev_mode=dev_mode)
        self.mode = "custom"
        self._build_ui()
        self._on_fields_change()

    def _build_ui(self) -> None:
        config_frame = tk.Frame(self.frame, bg="#f9fafb", relief=tk.RIDGE, bd=1)
        config_frame.pack(fill=tk.X, padx=6, pady=4)

        # Scenario name
        tk.Label(config_frame, text="Scenario name:", bg="#f9fafb", font=("Segoe UI", 10)).grid(
            row=0, column=0, padx=8, pady=6, sticky="w")
        self._name_var = tk.StringVar()
        tk.Entry(config_frame, textvariable=self._name_var, width=40, font=("Segoe UI", 10)).grid(
            row=0, column=1, padx=4, pady=6, sticky="ew")

        # Persona text
        tk.Label(config_frame, text="Persona / context:", bg="#f9fafb", font=("Segoe UI", 10)).grid(
            row=1, column=0, padx=8, pady=(6, 0), sticky="nw")
        self._persona_text = tk.Text(config_frame, height=5, font=("Segoe UI", 10), wrap=tk.WORD)
        self._persona_text.grid(row=1, column=1, padx=4, pady=6, sticky="ew")
        self._persona_text.bind("<KeyRelease>", lambda e: self._on_fields_change())

        # Eval template
        tk.Label(config_frame, text="Eval template:", bg="#f9fafb", font=("Segoe UI", 10)).grid(
            row=2, column=0, padx=8, pady=6, sticky="w")
        self._eval_var = tk.StringVar(value="(none)")
        templates = ["(none)"] + _list_eval_templates()
        self._eval_cb = ttk.Combobox(config_frame, textvariable=self._eval_var, values=templates, width=24, state="readonly")
        self._eval_cb.grid(row=2, column=1, padx=4, pady=6, sticky="w")
        self._eval_cb.bind("<<ComboboxSelected>>", self._on_eval_change)

        # Custom criteria
        tk.Label(config_frame, text="Custom eval criteria:", bg="#f9fafb", font=("Segoe UI", 10)).grid(
            row=3, column=0, padx=8, pady=(6, 0), sticky="nw")
        self._criteria_text = tk.Text(config_frame, height=3, font=("Segoe UI", 10), wrap=tk.WORD)
        self._criteria_text.grid(row=3, column=1, padx=4, pady=6, sticky="ew")

        # Buttons
        btn_frame = tk.Frame(config_frame, bg="#f9fafb")
        btn_frame.grid(row=4, column=1, padx=4, pady=6, sticky="w")
        ttk.Button(btn_frame, text="Save as JSON", command=self._save_scenario).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Load saved scenario", command=self._load_scenario).pack(side=tk.LEFT, padx=4)

        config_frame.columnconfigure(1, weight=1)

        # Session area
        session_container = tk.Frame(self.frame)
        session_container.pack(fill=tk.BOTH, expand=True)
        self._build_session_ui(session_container)

    def _on_fields_change(self) -> None:
        persona = self._persona_text.get("1.0", tk.END).strip()
        name = self._name_var.get().strip() or "custom"
        self.current_case = {
            "id": name,
            "patient_name": name,
            "persona_description": persona,
        }
        self._on_eval_change()

    def _on_eval_change(self, event=None) -> None:
        tpl = self._eval_var.get()
        if tpl == "(none)":
            criteria = self._criteria_text.get("1.0", tk.END).strip()
            if criteria:
                self.current_eval = {
                    "name": "Custom",
                    "output_sections": ["scores", "corrections", "anki_cards", "summary"],
                    "metrics": {
                        "grammar": {"label": "Grammar & Language", "anchors": {}},
                        "medical_accuracy": {"label": "Content Accuracy", "anchors": {}},
                        "clinical_reasoning": {"label": "Reasoning / Structure", "anchors": {}},
                        "communication_fluency": {"label": "Fluency", "anchors": {}},
                    },
                    "checklist": [],
                    "empathy_markers": [],
                    "custom_criteria_prose": criteria,
                }
            else:
                self.current_eval = None
        else:
            self.current_eval = _load_eval(tpl)

    def _save_scenario(self) -> None:
        persona = self._persona_text.get("1.0", tk.END).strip()
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Save Scenario", "Enter a scenario name first.")
            return
        data = {
            "id": name,
            "persona_description": persona,
            "eval_template": self._eval_var.get(),
            "custom_criteria": self._criteria_text.get("1.0", tk.END).strip(),
        }
        os.makedirs(config.CUSTOM_DIR, exist_ok=True)
        # Strip characters that are invalid in Windows filenames.
        import re
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ") or "custom"
        path = os.path.join(config.CUSTOM_DIR, f"{safe_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Save Scenario", f"Saved to {path}")

    def _load_scenario(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=config.CUSTOM_DIR,
            filetypes=[("JSON files", "*.json")],
            title="Load Custom Scenario",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._name_var.set(data.get("id", ""))
            self._persona_text.delete("1.0", tk.END)
            self._persona_text.insert("1.0", data.get("persona_description", ""))
            tpl = data.get("eval_template", "(none)")
            if tpl in self._eval_cb["values"]:
                self._eval_var.set(tpl)
            self._criteria_text.delete("1.0", tk.END)
            self._criteria_text.insert("1.0", data.get("custom_criteria", ""))
            self._on_fields_change()
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))

    def _build_system_prompt(self) -> str:
        persona = self._persona_text.get("1.0", tk.END).strip()
        return build_custom_prompt(persona or "You are a helpful conversational partner.")
