import tkinter as tk
from tkinter import ttk, messagebox

import config
from app.db.queries import get_setting, set_setting


class MainWindow:
    def __init__(self, dev_mode: bool = False):
        self.dev_mode = dev_mode
        self.root = tk.Tk()
        self.root.title(config.APP_TITLE + (" — DEV MODE" if dev_mode else ""))
        self.root.geometry(config.WINDOW_SIZE)
        self.root.minsize(800, 560)

        self._restore_geometry()
        self._apply_theme()
        self._build_menubar()
        self._build_notebook()

    def _restore_geometry(self) -> None:
        geom = get_setting("window_geometry")
        if geom:
            try:
                self.root.geometry(geom)
            except Exception:
                pass

    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        available = style.theme_names()
        for preferred in ("vista", "winnative", "clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break

        try:
            dpi = max(72, round(self.root.winfo_fpixels("1i")))
            scale_factor = dpi / 96.0
        except Exception:
            scale_factor = 1.0

        # Scale Treeview row height to prevent vertical row text overlapping on high-DPI screens
        row_height = int(24 * scale_factor)
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=row_height)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        style.configure("TNotebook.Tab", padding=[12, 6], font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=[8, 4])
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Anki Deck…", command=self._export_anki)
        file_menu.add_command(label="Export Docx Report…", command=self._export_docx)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Session History", command=self._show_history)
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Preferences…", command=self._show_preferences)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        from app.ui.encounter_tab import EncounterTab
        from app.ui.interview_tab import InterviewTab
        from app.ui.custom_tab import CustomTab
        from app.ui.history_tab import HistoryTab
        from app.ui.dashboard_tab import DashboardTab

        self.encounter_tab = EncounterTab(self.notebook, dev_mode=self.dev_mode)
        self.interview_tab = InterviewTab(self.notebook, dev_mode=self.dev_mode)
        self.custom_tab = CustomTab(self.notebook, dev_mode=self.dev_mode)
        self.history_tab = HistoryTab(self.notebook)
        self.dashboard_tab = DashboardTab(self.notebook)

        self.notebook.add(self.dashboard_tab.frame, text="Dashboard")
        self.notebook.add(self.encounter_tab.frame, text="Patient Encounter")
        self.notebook.add(self.interview_tab.frame, text="Residency Interview")
        self.notebook.add(self.custom_tab.frame, text="Custom Scenario")
        self.notebook.add(self.history_tab.frame, text="Session History")

    # ── Menu actions ──────────────────────────────────────────────────────────

    def _show_history(self) -> None:
        for i in range(self.notebook.index("end")):
            if "History" in self.notebook.tab(i, "text"):
                self.notebook.select(i)
                self.history_tab.refresh()
                return

    def _show_preferences(self) -> None:
        from app.ui.preferences_window import PreferencesWindow
        PreferencesWindow(self.root)

    def _export_anki(self) -> None:
        selected = getattr(self.history_tab, "get_selected_sessions", lambda: [])()
        if not selected:
            messagebox.showinfo("Export Anki", "Select one or more sessions in Session History first.")
            return
        from tkinter import filedialog
        from app.export.anki_exporter import export_sessions_to_apkg
        path = filedialog.asksaveasfilename(
            defaultextension=".apkg",
            filetypes=[("Anki Package", "*.apkg")],
            title="Save Anki Deck",
        )
        if path:
            saved = export_sessions_to_apkg(selected, path)
            if saved:
                messagebox.showinfo("Export Anki", f"Saved: {saved}")
            else:
                messagebox.showinfo("Export Anki", "No Anki cards found in the selected session(s) — nothing exported.")

    def _export_docx(self) -> None:
        selected = getattr(self.history_tab, "get_selected_sessions", lambda: [])()
        if not selected:
            messagebox.showinfo("Export Docx", "Select a session in Session History first.")
            return
        session = selected[0]
        from tkinter import filedialog
        from app.export.docx_exporter import generate_report, suggest_filename
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            initialfile=suggest_filename(session),
            title="Save Report",
        )
        if path:
            generate_report(session, path)
            messagebox.showinfo("Export Docx", f"Saved: {path}")

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About MedVoiceTrainer",
            "MedVoiceTrainer\n\nMedical English speaking practice for IMGs.\n\n"
            "Modes: Patient Encounter · Residency Interview · Custom Scenario\n"
            "Voice AI: Gemini Live · OpenAI Realtime\n"
            "Analysis: Claude API\n\nVersion 1.0",
        )

    def _on_quit(self) -> None:
        geom = self.root.geometry()
        set_setting("window_geometry", geom)
        self.root.destroy()

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)
        self.root.mainloop()
