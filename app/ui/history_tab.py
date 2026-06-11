import json
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Optional

from app.db import queries


class HistoryTab:
    def __init__(self, parent: ttk.Notebook):
        self.frame = tk.Frame(parent)
        self._selected_sessions: list[dict] = []
        self._all_sessions: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        # Session list
        list_frame = tk.Frame(self.frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        try:
            dpi = max(72, round(self.frame.winfo_fpixels("1i")))
            scale_factor = dpi / 96.0
        except Exception:
            scale_factor = 1.0

        columns = ("date", "mode", "case", "score", "duration")
        self._tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended", height=10)
        for col, label, width, anchor in [
            ("date", "Date", int(150 * scale_factor), "center"),
            ("mode", "Mode", int(100 * scale_factor), "center"),
            ("case", "Case / Scenario", int(240 * scale_factor), "w"),
            ("score", "Avg Score", int(100 * scale_factor), "center"),
            ("duration", "Duration", int(100 * scale_factor), "center"),
        ]:
            self._tree.heading(col, text=label, anchor=anchor)
            self._tree.column(col, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Action buttons
        btn_frame = tk.Frame(self.frame, bg="#f3f4f6", relief=tk.RIDGE, bd=1)
        btn_frame.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(btn_frame, text="View Feedback", command=self._view_feedback).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(btn_frame, text="Export Docx", command=self._export_docx).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(btn_frame, text="Export Anki", command=self._export_anki).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(btn_frame, text="Delete", command=self._delete_session).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.RIGHT, padx=6, pady=6)

        # Comparison bar
        self._compare_var = tk.StringVar(value="")
        compare_label = tk.Label(self.frame, textvariable=self._compare_var,
                                  font=("Segoe UI", 9, "italic"), foreground="#4b5563",
                                  wraplength=800, justify=tk.LEFT)
        compare_label.pack(padx=8, pady=2, anchor="w")

        # Score trend chart
        chart_frame = tk.Frame(self.frame, relief=tk.RIDGE, bd=1)
        chart_frame.pack(fill=tk.X, padx=6, pady=4)
        self._build_chart(chart_frame)

    def _build_chart(self, container: tk.Frame) -> None:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

            try:
                dpi = max(72, round(self.frame.winfo_fpixels("1i")))
            except Exception:
                dpi = 96
            self._fig = Figure(figsize=(8, 2.4), dpi=dpi, facecolor="#ffffff")
            self._ax = self._fig.add_subplot(111)
            self._ax.set_title("Score Trend (last 10 sessions)", fontsize=9)
            self._ax.set_ylim(0, 10)
            self._ax.tick_params(labelsize=8)
            self._fig.tight_layout(pad=1.0)

            self._canvas = FigureCanvasTkAgg(self._fig, master=container)
            self._canvas.get_tk_widget().pack(fill=tk.X, padx=4, pady=4)
            self._chart_available = True
        except Exception:
            self._chart_available = False
            tk.Label(container, text="matplotlib unavailable — install to see score trend chart.",
                     font=("Segoe UI", 9), foreground="#9ca3af").pack(pady=8)

    def refresh(self) -> None:
        self._all_sessions = queries.list_sessions(200)
        self._tree.delete(*self._tree.get_children())
        for s in self._all_sessions:
            avg = self._avg_score(s)
            score_str = f"{avg:.1f}" if avg is not None else "—"
            dur = s.get("duration_seconds") or 0
            dur_str = f"{dur // 60}m {dur % 60}s"
            try:
                from datetime import timezone
                dt = datetime.fromisoformat(s["created_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                date_str = dt.astimezone().strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = s.get("created_at", "")[:16]
            self._tree.insert("", tk.END, iid=str(s["id"]), values=(
                date_str,
                s.get("mode", "").capitalize(),
                s.get("case_name", ""),
                score_str,
                dur_str,
            ))
        self._update_chart()

    def _avg_score(self, s: dict) -> Optional[float]:
        scores = [s.get(k) for k in ("grammar_score", "medical_accuracy_score",
                                      "clinical_reasoning_score",
                                      "professionalism_score", "fluency_score")]
        valid = [v for v in scores if v is not None]
        return sum(valid) / len(valid) if valid else None

    def _on_select(self, event=None) -> None:
        selected_ids = self._tree.selection()
        self._selected_sessions = [
            s for s in self._all_sessions if str(s["id"]) in selected_ids
        ]
        if len(self._selected_sessions) == 1:
            self._show_comparison(self._selected_sessions[0])
        else:
            self._compare_var.set("")

    def _show_comparison(self, session: dict) -> None:
        case_id = session.get("case_id")
        if not case_id:
            self._compare_var.set("")
            return
        prior = queries.get_sessions_for_case(case_id)
        # Compare against the most recent attempt that came BEFORE this one
        # (the list is ordered most-recent-first).
        current_ts = session.get("created_at", "")
        prior = [
            p for p in prior
            if p["id"] != session["id"]
            and self._avg_score(p) is not None
            and p.get("created_at", "") < current_ts
        ]
        if not prior:
            self._compare_var.set("No prior sessions for this case.")
            return
        last = prior[0]
        parts = []
        for metric, col in [
            ("Grammar", "grammar_score"),
            ("Accuracy", "medical_accuracy_score"),
            ("Reasoning", "clinical_reasoning_score"),
            ("Professionalism", "professionalism_score"),
            ("Fluency", "fluency_score"),
        ]:
            curr = session.get(col)
            prev = last.get(col)
            if curr is not None and prev is not None:
                diff = curr - prev
                arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "—")
                parts.append(f"{metric} {arrow}{abs(diff):.1f}")
        if parts:
            self._compare_var.set("vs. your last attempt: " + " | ".join(parts))

    def _update_chart(self) -> None:
        if not self._chart_available:
            return
        sessions = list(reversed(self._all_sessions[:10]))
        dates = []
        grammar, accuracy, reasoning, professionalism, fluency = [], [], [], [], []
        for s in sessions:
            try:
                from datetime import timezone
                dt = datetime.fromisoformat(s["created_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dates.append(dt.astimezone().strftime("%m/%d"))
            except Exception:
                dates.append("")
            grammar.append(s.get("grammar_score"))
            accuracy.append(s.get("medical_accuracy_score"))
            reasoning.append(s.get("clinical_reasoning_score"))
            professionalism.append(s.get("professionalism_score"))
            fluency.append(s.get("fluency_score"))

        self._ax.clear()
        self._ax.set_title("Score Trend (last 10 sessions)", fontsize=9)
        self._ax.set_ylim(0, 10)
        self._ax.tick_params(labelsize=8)
        xs = range(len(dates))
        plotted_any = False
        for label, vals, color in [
            ("Grammar", grammar, "#3b82f6"),
            ("Accuracy", accuracy, "#10b981"),
            ("Reasoning", reasoning, "#f59e0b"),
            ("Professionalism", professionalism, "#8b5cf6"),
            ("Fluency", fluency, "#ef4444"),
        ]:
            y = [v for v in vals if v is not None]
            x = [i for i, v in enumerate(vals) if v is not None]
            if x:
                self._ax.plot(x, y, marker="o", label=label, color=color, linewidth=1.5, markersize=4)
                plotted_any = True
        if dates:
            self._ax.set_xticks(list(xs))
            self._ax.set_xticklabels(dates, fontsize=7)
        if plotted_any:
            self._ax.legend(loc="upper left", fontsize=7, ncol=5)
        self._fig.tight_layout(pad=1.0)
        self._canvas.draw()

    def get_selected_sessions(self) -> list[dict]:
        return self._selected_sessions

    # ── Actions ───────────────────────────────────────────────────────────────

    def _view_feedback(self) -> None:
        if not self._selected_sessions:
            messagebox.showinfo("View Feedback", "Select a session first.")
            return
        session = self._selected_sessions[0]
        analysis = {}
        if session.get("raw_claude_response"):
            try:
                analysis = json.loads(session["raw_claude_response"])
            except Exception:
                pass
        if not analysis:
            messagebox.showinfo("View Feedback", "No analysis data for this session.")
            return
        from app.ui.feedback_window import FeedbackWindow
        FeedbackWindow(self.frame, session=session, analysis=analysis)

    def _export_docx(self) -> None:
        if not self._selected_sessions:
            messagebox.showinfo("Export Docx", "Select a session first.")
            return
        session = self._selected_sessions[0]
        from tkinter import filedialog
        from app.export.docx_exporter import generate_report, suggest_filename
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            initialfile=suggest_filename(session),
        )
        if path:
            generate_report(session, path)
            messagebox.showinfo("Export Docx", f"Saved: {path}")

    def _export_anki(self) -> None:
        if not self._selected_sessions:
            messagebox.showinfo("Export Anki", "Select one or more sessions first.")
            return
        from tkinter import filedialog
        from app.export.anki_exporter import export_sessions_to_apkg
        path = filedialog.asksaveasfilename(
            defaultextension=".apkg",
            filetypes=[("Anki Package", "*.apkg")],
        )
        if path:
            saved = export_sessions_to_apkg(self._selected_sessions, path)
            if saved:
                messagebox.showinfo("Export Anki", f"Saved: {saved}")
            else:
                messagebox.showinfo("Export Anki", "No Anki cards found in the selected session(s) — nothing exported.")

    def _delete_session(self) -> None:
        if not self._selected_sessions:
            messagebox.showinfo("Delete", "Select a session first.")
            return
        count = len(self._selected_sessions)
        if not messagebox.askyesno("Confirm Delete", f"Delete {count} session(s)? This cannot be undone."):
            return
        for s in self._selected_sessions:
            queries.delete_session(s["id"])
        self._selected_sessions = []
        self.refresh()
