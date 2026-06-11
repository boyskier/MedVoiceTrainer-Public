import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import anthropic

from app.db import queries

# Injected first user turn that kicks off the Socratic debrief. Stored in the
# message history (so the API always receives a user-first, alternating list)
# but hidden from the chat display.
_KICKOFF_MESSAGE = "Hi Dr. Tutor, I'm ready for the debrief."


class DebriefWindow:
    def __init__(self, parent: tk.Widget, session: dict, analysis: dict):
        self.session = session
        self.analysis = analysis

        try:
            from app.db.queries import get_setting
            self.backend = get_setting("feedback_backend", "claude")
        except Exception:
            self.backend = "claude"

        if self.backend == "gemini":
            self.api_key = os.environ.get("GEMINI_API_KEY", "")
            self.api_key_name = "GEMINI_API_KEY"
        elif self.backend == "openai":
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
            self.api_key_name = "OPENAI_API_KEY"
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            self.api_key_name = "ANTHROPIC_API_KEY"

        self.win = tk.Toplevel(parent)
        self.win.title("Interactive Debrief with AI Tutor")
        self.win.geometry("600x500")
        self.win.resizable(True, True)

        self._messages = []
        saved_chat = self.session.get("debrief_chat")
        if saved_chat:
            try:
                self._messages = json.loads(saved_chat)
            except Exception:
                self._messages = []

        self._build_ui()
        self._init_conversation()

    def _save_chat_to_db(self) -> None:
        if self.session.get("id"):
            queries.save_debrief_chat(self.session["id"], json.dumps(self._messages))

    def _build_ui(self) -> None:
        chat_frame = tk.Frame(self.win)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.chat_display = tk.Text(chat_frame, state=tk.DISABLED, wrap=tk.WORD, font=("Segoe UI", 10))
        vsb = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat_display.yview)
        self.chat_display.configure(yscrollcommand=vsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_display.tag_configure("system", foreground="#6b7280", font=("Segoe UI", 9, "italic"))
        self.chat_display.tag_configure("user", foreground="#1d4ed8", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("ai", foreground="#047857", font=("Segoe UI", 10))

        input_frame = tk.Frame(self.win)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.entry = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self._send_message())

        self.send_btn = ttk.Button(input_frame, text="Send", command=self._send_message)
        self.send_btn.pack(side=tk.RIGHT)

    def _init_conversation(self) -> None:
        if not self.api_key:
            self._append_text("System", f"{self.api_key_name} is not set. Cannot start debriefing.", "system")
            self.entry.config(state=tk.DISABLED)
            self.send_btn.config(state=tk.DISABLED)
            return

        transcript = self.session.get("raw_transcript", "[]")
        
        system_prompt = f"""You are a Senior Attending Physician acting as a mentor.
You are debriefing a medical student after a simulated clinical encounter.
Review the following transcript and your previous analysis, then engage in a Socratic dialogue to help them reflect on their performance.
Keep your responses relatively brief (1-2 paragraphs). Ask guiding questions rather than just lecturing.

=== ENCOUNTER TRANSCRIPT ===
{transcript}

=== FEEDBACK GIVEN ===
{json.dumps(self.analysis, indent=2)}

Begin by warmly welcoming the student and asking an open-ended question about how they felt the encounter went.
"""
        self.system_prompt = system_prompt
        
        if self._messages:
            for msg in self._messages:
                role = msg.get("role")
                text = msg.get("content", "")
                if role == "user":
                    if text == _KICKOFF_MESSAGE:
                        continue  # Skip initial system-injected trigger
                    self._append_text("You", text, "user")
                elif role == "assistant":
                    self._append_text("AI Tutor", text, "ai")
        else:
            self._append_text("System", "Connecting to AI Tutor...", "system")
            # Persist the kickoff turn so the message history always starts with a
            # user turn — the Anthropic API rejects a history that begins with an
            # assistant message (which is what happened on the user's 2nd turn).
            self._messages.append({"role": "user", "content": _KICKOFF_MESSAGE})
            self._generate_ai_response()

    def _append_text(self, sender: str, text: str, tag: str) -> None:
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"{sender}:\n", tag)
        self.chat_display.insert(tk.END, f"{text}\n\n", tag)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _send_message(self) -> None:
        user_text = self.entry.get().strip()
        if not user_text:
            return

        self.entry.delete(0, tk.END)
        self._append_text("You", user_text, "user")
        self._messages.append({"role": "user", "content": user_text})
        self._save_chat_to_db()
        
        self.entry.config(state=tk.DISABLED)
        self.send_btn.config(state=tk.DISABLED)
        
        self._generate_ai_response()

    def _generate_ai_response(self) -> None:
        def worker():
            try:
                from app.analysis.analysis_providers import ANALYSIS_MODELS
                model_name = ANALYSIS_MODELS.get(self.backend, "claude-sonnet-4-6")

                if self.backend == "gemini":
                    from google import genai
                    from google.genai import types
                    client = genai.Client(api_key=self.api_key)
                    contents = []
                    for msg in self._messages:
                        contents.append(
                            types.Content(
                                role="user" if msg["role"] == "user" else "model",
                                parts=[types.Part.from_text(text=msg["content"])]
                            )
                        )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=self.system_prompt,
                            max_output_tokens=1024,
                        ),
                    )
                    ai_text = (resp.text or "").strip()

                elif self.backend == "openai":
                    import openai
                    client = openai.OpenAI(api_key=self.api_key)
                    msgs = [{"role": "system", "content": self.system_prompt}]
                    for msg in self._messages:
                        msgs.append({"role": msg["role"], "content": msg["content"]})
                    
                    # Determine if reasoning model
                    kwargs = {}
                    if "gpt-5" in model_name:
                        kwargs["max_completion_tokens"] = 1024
                        kwargs["reasoning_effort"] = "low"
                    else:
                        kwargs["max_tokens"] = 1024

                    resp = client.chat.completions.create(
                        model=model_name,
                        messages=msgs,
                        **kwargs
                    )
                    ai_text = (resp.choices[0].message.content or "").strip()

                else:
                    client = anthropic.Anthropic(api_key=self.api_key)
                    
                    msgs = self._messages.copy()
                    # The Anthropic API requires the history to begin with a user
                    # turn. New sessions persist the kickoff turn up front; this also
                    # repairs legacy chats saved before that fix (which start with an
                    # assistant turn) so resuming them doesn't 400.
                    if not msgs or msgs[0].get("role") != "user":
                        msgs = [{"role": "user", "content": _KICKOFF_MESSAGE}] + msgs

                    response = client.messages.create(
                        model=model_name,
                        max_tokens=1024,
                        system=self.system_prompt,
                        messages=msgs,
                    )
                    ai_text = response.content[0].text.strip()
                
                self._messages.append({"role": "assistant", "content": ai_text})
                self._save_chat_to_db()
                
                self.win.after(0, lambda: self._on_ai_response_success(ai_text))
            except Exception as e:
                self.win.after(0, lambda: self._on_ai_response_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_response_success(self, text: str) -> None:
        self._append_text("AI Tutor", text, "ai")
        self.entry.config(state=tk.NORMAL)
        self.send_btn.config(state=tk.NORMAL)
        self.entry.focus_set()

    def _on_ai_response_error(self, error: str) -> None:
        self._append_text("System Error", str(error), "system")
        self.entry.config(state=tk.NORMAL)
        self.send_btn.config(state=tk.NORMAL)
