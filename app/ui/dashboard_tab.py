import json
import tkinter as tk
from tkinter import ttk
from app.db import queries

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _MATPLOTLIB_AVAILABLE = True
except Exception:
    _MATPLOTLIB_AVAILABLE = False


class DashboardTab:
    def __init__(self, notebook: ttk.Notebook):
        self.frame = tk.Frame(notebook, bg="#f9fafb")
        self._chart_available = _MATPLOTLIB_AVAILABLE
        self._build_ui()
        if not self._chart_available:
            return
        # Refresh only when this tab is actually selected. Binding to <Visibility>
        # would re-query the DB and redraw the whole figure on every expose event
        # (tab switches, window restores, partial uncovering) — needlessly costly.
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    def _on_tab_changed(self, event) -> None:
        try:
            if event.widget.select() == str(self.frame):
                self.refresh()
        except Exception:
            pass

    def _build_ui(self) -> None:
        header = tk.Frame(self.frame, bg="#ffffff", relief=tk.RIDGE, bd=1)
        header.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(
            header,
            text="Longitudinal Progress Dashboard",
            font=("Segoe UI", 16, "bold"),
            bg="#ffffff"
        ).pack(side=tk.LEFT, padx=16, pady=12)

        ttk.Button(header, text="Refresh", command=self.refresh).pack(side=tk.RIGHT, padx=16, pady=12)

        self.chart_frame = tk.Frame(self.frame, bg="#f9fafb")
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        if not self._chart_available:
            tk.Label(
                self.chart_frame,
                text="matplotlib unavailable — install it to see the progress dashboard.",
                font=("Segoe UI", 11), bg="#f9fafb", foreground="#9ca3af",
            ).pack(pady=40)
            return

        # Render at the real screen DPI (the app is DPI-aware, so a hardcoded
        # dpi=100 looks tiny/blurry on scaled displays), and keep the chart a
        # fixed sensible size centred in the tab instead of ballooning to fill
        # a maximized window.
        try:
            dpi = max(72, round(self.frame.winfo_fpixels("1i")))
        except Exception:
            dpi = 100
        self.figure = Figure(figsize=(9, 5), dpi=dpi)
        self.ax = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(expand=True)

    def refresh(self) -> None:
        if not self._chart_available:
            return
        sessions = queries.list_sessions(limit=20)
        # Reverse to get chronological order
        sessions.reverse()
        
        self.ax.clear()

        if not sessions:
            self.ax.text(0.5, 0.5, "No session data available.", 
                         ha='center', va='center', fontsize=12, color='gray')
            self.canvas.draw()
            return

        dates = []
        metrics = {
            "grammar": [],
            "medical_accuracy": [],
            "clinical_reasoning": [],
            "professionalism": [],
            "fluency": []
        }

        for s in sessions:
            try:
                analysis = json.loads(s.get("raw_claude_response") or "{}")
                scores = analysis.get("overall_scores", {})
                if not scores:
                    continue

                # Use short date format "MM-DD"
                try:
                    from datetime import timezone, datetime
                    dt = datetime.fromisoformat(s.get("created_at", ""))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    date_str = dt.astimezone().strftime("%m-%d")
                except Exception:
                    date_str = s.get("created_at", "")[5:10] if s.get("created_at") else f"S{s.get('id')}"
                dates.append(date_str)

                metrics["grammar"].append(scores.get("grammar"))
                metrics["medical_accuracy"].append(scores.get("medical_accuracy"))
                metrics["clinical_reasoning"].append(scores.get("clinical_reasoning"))
                metrics["professionalism"].append(scores.get("professionalism"))
                # Both names are used in different eval templates
                fluency_score = scores.get("fluency")
                if fluency_score is None:
                    fluency_score = scores.get("communication_fluency")
                metrics["fluency"].append(fluency_score)

            except Exception:
                continue

        if not dates:
            self.ax.text(0.5, 0.5, "No scored sessions available.", 
                         ha='center', va='center', fontsize=12, color='gray')
            self.canvas.draw()
            return

        x = range(len(dates))
        
        # Plot each metric, filtering out None values
        colors = {
            "grammar": "#3b82f6", # Blue
            "medical_accuracy": "#ef4444", # Red
            "clinical_reasoning": "#8b5cf6", # Purple
            "professionalism": "#10b981", # Green
            "fluency": "#f59e0b" # Amber
        }
        
        labels = {
            "grammar": "Grammar",
            "medical_accuracy": "Medical Accuracy",
            "clinical_reasoning": "Clinical Reasoning",
            "professionalism": "Professionalism",
            "fluency": "Fluency"
        }

        plotted_any = False
        for key, vals in metrics.items():
            # Only plot points where we actually have a score
            x_valid = [i for i, v in enumerate(vals) if v is not None]
            y_valid = [v for v in vals if v is not None]

            if x_valid:
                self.ax.plot(x_valid, y_valid, marker='o', linestyle='-', linewidth=2,
                             color=colors[key], label=labels[key])
                plotted_any = True

        self.ax.set_ylim(0, 10.5)
        self.ax.set_ylabel("Score (0-10)")
        self.ax.set_title("Recent Performance Trends (Last 20 Sessions)")

        self.ax.set_xticks(x)
        self.ax.set_xticklabels(dates, rotation=45, ha='right')

        if plotted_any:
            self.ax.legend(loc='lower right')
        self.ax.grid(True, linestyle='--', alpha=0.7)
        self.figure.tight_layout()
        
        self.canvas.draw()
