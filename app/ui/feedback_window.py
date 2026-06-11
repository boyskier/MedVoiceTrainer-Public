import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional

import config
from app.db.queries import get_setting, save_docx_path


class FeedbackWindow:
    def __init__(self, parent: tk.Widget, session: dict, analysis: dict):
        self.session = session
        self.analysis = analysis

        self.win = tk.Toplevel(parent)
        self.win.title("Session Feedback")
        self.win.geometry(config.FEEDBACK_WINDOW_SIZE)
        self.win.resizable(True, True)

        notebook = ttk.Notebook(self.win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._build_scores_tab(notebook)
        self._build_checklist_tab(notebook)
        self._build_soap_tab(notebook)
        self._build_corrections_tab(notebook)
        self._build_summary_tab(notebook)

        # Bottom action bar
        action_bar = tk.Frame(self.win, bg="#f3f4f6", relief=tk.RIDGE, bd=1)
        action_bar.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(action_bar, text="Export Anki", command=self._export_anki).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(action_bar, text="Save Docx Report", command=self._save_docx).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(action_bar, text="Debrief with AI Tutor", command=self._open_debrief).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(action_bar, text="Close", command=self.win.destroy).pack(side=tk.RIGHT, padx=6, pady=6)

        # Auto-save docx if enabled
        if get_setting("auto_save_docx") == "true":
            self._auto_save_docx()

    # ── Scores Tab ────────────────────────────────────────────────────────────

    def _build_scores_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb)
        nb.add(frame, text="Scores")

        scores = self.analysis.get("overall_scores", {})
        delta = self.analysis.get("self_assessment_delta", {})
        self_scores = {
            "grammar": self.session.get("self_grammar"),
            "medical_accuracy": self.session.get("self_medical_accuracy"),
            "clinical_reasoning": self.session.get("self_clinical_reasoning"),
            "professionalism": self.session.get("self_professionalism"),
            "communication_fluency": self.session.get("self_fluency"),
            "fluency": self.session.get("self_fluency"),
        }

        canvas = tk.Canvas(frame, bg="#ffffff")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg="#ffffff")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        for metric, score in scores.items():
            try:
                score = float(score)
            except (TypeError, ValueError):
                continue
            card = tk.Frame(inner, bg="#f0f9ff", relief=tk.GROOVE, bd=1)
            card.pack(fill=tk.X, padx=12, pady=6)

            label = metric.replace("_", " ").title()
            tk.Label(card, text=label, font=("Segoe UI", 11, "bold"),
                     bg="#f0f9ff").pack(anchor="w", padx=10, pady=(8, 2))

            bar_frame = tk.Frame(card, bg="#f0f9ff")
            bar_frame.pack(fill=tk.X, padx=10, pady=4)

            # Claude score bar
            self._draw_score_bar(bar_frame, f"Claude: {score:.1f}/10", score, "#3b82f6")

            self_val = self_scores.get(metric)
            if self_val is not None:
                self_val = float(self_val)
                self._draw_score_bar(bar_frame, f"Self: {self_val:.1f}/10", self_val, "#10b981")
                d = delta.get(metric)
                try:
                    d = float(d) if d is not None else None
                except (TypeError, ValueError):
                    d = None
                if d is not None:
                    direction = "You underestimated yourself" if d > 0 else ("You overestimated yourself" if d < 0 else "Accurate self-assessment")
                    color = "#16a34a" if d > 0 else ("#dc2626" if d < 0 else "#4b5563")
                    tk.Label(card, text=f"Delta: {d:+.1f}  ({direction})",
                             font=("Segoe UI", 9, "italic"), bg="#f0f9ff", foreground=color
                             ).pack(anchor="w", padx=10, pady=(0, 8))
                    
                    if abs(d) >= 2.0:
                        reflection_text = f"Reflection Prompt: AI rated {label} as {score:.1f}, but you rated yourself {self_val:.1f}. Why do you think there is a difference?"
                        tk.Label(card, text=reflection_text, font=("Segoe UI", 9, "bold"),
                                 bg="#fef08a", foreground="#854d0e", wraplength=650, justify=tk.LEFT
                                 ).pack(anchor="w", fill=tk.X, padx=10, pady=(0, 8))

    def _draw_score_bar(self, parent: tk.Frame, label: str, value: float, color: str) -> None:
        row = tk.Frame(parent, bg="#f0f9ff")
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=18, anchor="w", font=("Segoe UI", 10),
                 bg="#f0f9ff").pack(side=tk.LEFT)
        bar_bg = tk.Frame(row, bg="#e5e7eb", width=300, height=16)
        bar_bg.pack(side=tk.LEFT, padx=4)
        bar_bg.pack_propagate(False)
        clamped = max(0.0, min(value, 10.0))
        fill_w = int(300 * clamped / 10)
        tk.Frame(bar_bg, bg=color, width=fill_w, height=16).place(x=0, y=0)

    # ── Checklist Tab ─────────────────────────────────────────────────────────

    def _build_checklist_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb)
        nb.add(frame, text="Checklist")

        checklist = self.analysis.get("checklist_results", [])
        if not checklist:
            tk.Label(frame, text="No checklist data.", font=("Segoe UI", 10),
                     foreground="#9ca3af").pack(pady=40)
            return

        passed_n = sum(1 for i in checklist if i.get("passed"))
        required = [i for i in checklist if i.get("required")]
        req_passed_n = sum(1 for i in required if i.get("passed"))
        req_ok = req_passed_n == len(required)
        summary = f"Passed {passed_n}/{len(checklist)}"
        if required:
            summary += f"  ·  Required: {req_passed_n}/{len(required)}"
            if not req_ok:
                summary += "  — review the missed required items below"
        tk.Label(frame, text=summary, font=("Segoe UI", 10, "bold"),
                 foreground="#16a34a" if req_ok else "#dc2626",
                 ).pack(anchor="w", padx=10, pady=(8, 0))

        try:
            dpi = max(72, round(frame.winfo_fpixels("1i")))
            scale_factor = dpi / 96.0
        except Exception:
            scale_factor = 1.0

        tree = ttk.Treeview(frame, columns=("required", "result", "evidence"), show="tree headings")
        tree.heading("#0", text="Item")
        tree.heading("required", text="Required")
        tree.heading("result", text="Result")
        tree.heading("evidence", text="Evidence")
        tree.column("#0", width=int(280 * scale_factor))
        tree.column("required", width=int(70 * scale_factor), anchor="center")
        tree.column("result", width=int(70 * scale_factor), anchor="center")
        tree.column("evidence", width=int(280 * scale_factor))

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        for item in checklist:
            passed = item.get("passed")
            result_text = "✓ Pass" if passed else "✗ Fail"
            tag = "pass" if passed else "fail"
            tree.insert("", tk.END,
                        text=item.get("item", ""),
                        values=(
                            "Yes" if item.get("required") else "No",
                            result_text,
                            item.get("evidence") or "",
                        ),
                        tags=(tag,))

        tree.tag_configure("pass", background="#dcfce7")
        tree.tag_configure("fail", background="#fee2e2")

    # ── SOAP Tab ──────────────────────────────────────────────────────────────

    def _build_soap_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb)
        nb.add(frame, text="SOAP Note")

        soap = self.analysis.get("soap_note")
        ref_soap_str = self.session.get("reference_soap")
        if not ref_soap_str and self.session.get("raw_case_json"):
            try:
                case_data = json.loads(self.session["raw_case_json"])
                ref_soap = case_data.get("reference_soap")
                if ref_soap:
                    ref_soap_str = json.dumps(ref_soap)
            except Exception:
                pass

        if not soap and not ref_soap_str:
            tk.Label(frame, text="No SOAP data for this session.", font=("Segoe UI", 10),
                     foreground="#9ca3af").pack(pady=40)
            return

        paned = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        def make_soap_panel(title: str, soap_dict: Optional[dict]) -> tk.Frame:
            panel = tk.Frame(paned)
            tk.Label(panel, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=4)
            if not soap_dict:
                tk.Label(panel, text="N/A", foreground="#9ca3af", font=("Segoe UI", 9)).pack()
                return panel
            for key, label in [("subjective", "S"), ("objective", "O"), ("assessment", "A"), ("plan", "P")]:
                tk.Label(panel, text=f"{label}:", font=("Segoe UI", 10, "bold"), foreground="#1d4ed8").pack(anchor="w", padx=4, pady=(6, 0))
                t = tk.Text(panel, wrap=tk.WORD, height=4, font=("Segoe UI", 10), bg="#f8fafc", relief=tk.FLAT)
                t.insert("1.0", soap_dict.get(key, ""))
                t.config(state=tk.DISABLED)
                t.pack(fill=tk.X, padx=4, pady=2)
            return panel

        left = make_soap_panel("Your SOAP Note", soap)
        paned.add(left, weight=1)

        ref_soap = None
        if ref_soap_str:
            try:
                ref_soap = json.loads(ref_soap_str) if isinstance(ref_soap_str, str) else ref_soap_str
            except Exception:
                pass
        right = make_soap_panel("Reference SOAP (Model Answer)", ref_soap)
        paned.add(right, weight=1)

    # ── Corrections Tab ───────────────────────────────────────────────────────

    def _build_corrections_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb)
        nb.add(frame, text="Corrections")

        corrections = self.analysis.get("corrections", [])
        if not corrections:
            tk.Label(frame, text="No corrections — great work!",
                     font=("Segoe UI", 10), foreground="#16a34a").pack(pady=40)
            return

        canvas = tk.Canvas(frame, bg="#ffffff")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg="#ffffff")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        for i, corr in enumerate(corrections, 1):
            card = tk.Frame(inner, bg="#fff7ed", relief=tk.GROOVE, bd=1)
            card.pack(fill=tk.X, padx=10, pady=6)
            tk.Label(card, text=f"#{i}  [Turn {corr.get('turn_index', '?')}]",
                     font=("Segoe UI", 9, "bold"), bg="#fff7ed", foreground="#92400e").pack(anchor="w", padx=8, pady=(6, 2))
            tk.Label(card, text=f"Original: {corr.get('original', '')}",
                     font=("Segoe UI", 10), bg="#fff7ed", foreground="#dc2626",
                     wraplength=680, justify=tk.LEFT).pack(anchor="w", padx=8, pady=2)
            tk.Label(card, text=f"Corrected: {corr.get('corrected', '')}",
                     font=("Segoe UI", 10), bg="#fff7ed", foreground="#16a34a",
                     wraplength=680, justify=tk.LEFT).pack(anchor="w", padx=8, pady=2)
            tk.Label(card, text=corr.get("explanation", ""),
                     font=("Segoe UI", 9, "italic"), bg="#fff7ed", foreground="#6b7280",
                     wraplength=680, justify=tk.LEFT).pack(anchor="w", padx=8, pady=(2, 8))

    # ── Summary Tab ───────────────────────────────────────────────────────────

    def _build_summary_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb)
        nb.add(frame, text="Summary")

        summary = self.analysis.get("summary_feedback", "")

        t = tk.Text(frame, wrap=tk.WORD, font=("Segoe UI", 11), bg="#f8fafc", relief=tk.FLAT,
                    padx=16, pady=12)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        t.pack(fill=tk.BOTH, expand=True)
        t.insert("1.0", summary or "No summary feedback available.")
        t.config(state=tk.DISABLED)

        # Anki cards preview
        cards = self.analysis.get("anki_cards", [])
        if cards:
            tk.Label(frame, text=f"{len(cards)} Anki card(s) generated — use 'Export Anki' to save.",
                     font=("Segoe UI", 9, "italic"), foreground="#6b7280").pack(pady=4)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_debrief(self) -> None:
        from app.ui.debrief_window import DebriefWindow
        DebriefWindow(self.win, self.session, self.analysis)

    def _export_anki(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".apkg",
            filetypes=[("Anki Package", "*.apkg")],
            title="Save Anki Deck",
        )
        if not path:
            return
        from app.export.anki_exporter import export_sessions_to_apkg
        # The fresh analysis may not be in self.session yet (it was loaded at
        # window-open time) — re-read the row so the cards are found.
        session = self.session
        sid = session.get("id")
        if sid:
            from app.db.queries import get_session
            session = get_session(sid) or session
        saved = export_sessions_to_apkg([session], path)
        if saved:
            messagebox.showinfo("Export Anki", f"Saved: {saved}")
        else:
            messagebox.showinfo("Export Anki", "No Anki cards found for this session — nothing exported.")

    def _save_docx(self) -> None:
        from app.export.docx_exporter import generate_report, suggest_filename
        export_dir = get_setting("docx_export_dir")
        initial_dir = export_dir if export_dir and os.path.isdir(export_dir) else None
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            initialfile=suggest_filename(self.session),
            initialdir=initial_dir,
            title="Save Docx Report",
        )
        if path:
            generate_report(self.session, path)
            save_docx_path(self.session.get("id", 0), path)
            messagebox.showinfo("Save Docx", f"Saved: {path}")

    def _auto_save_docx(self) -> None:
        from app.export.docx_exporter import generate_report, suggest_filename
        export_dir = get_setting("docx_export_dir")
        if not export_dir or not os.path.isdir(export_dir):
            return
        fname = suggest_filename(self.session)
        path = os.path.join(export_dir, fname)
        try:
            generate_report(self.session, path)
            save_docx_path(self.session.get("id", 0), path)
        except Exception:
            pass
