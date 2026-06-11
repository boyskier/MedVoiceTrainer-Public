# MedVoiceTrainer User Guide

**Target Audience:** IMGs (International Medical Graduates) and medical students preparing for OSCE, OET, or US Internal Medicine residency interviews.

---

## Table of Contents

1. [API Key Setup](#1-api-key-setup)
2. [Installation and Execution](#2-installation-and-execution)
3. [UI Layout Overview](#3-ui-layout-overview)
4. [Patient Encounters](#4-patient-encounters)
5. [Residency Interviews](#5-residency-interviews)
6. [Custom Scenarios](#6-custom-scenarios)
7. [Understanding the Feedback Window](#7-understanding-the-feedback-window)
8. [Session History Management](#8-session-history-management)
9. [Exporting to Anki](#9-exporting-to-anki)
10. [Saving Word Reports](#10-saving-word-reports)
11. [Checking API Costs](#11-checking-api-costs)
12. [Preferences Configuration](#12-preferences-configuration)
13. [FAQ](#13-faq)
14. [Scoring Rubric](#14-scoring-rubric)
15. [Case List](#15-case-list)

---

## 1. API Key Setup

MedVoiceTrainer supports Google Gemini, Anthropic Claude, and OpenAI.

### 💡 Recommended Setup (Gemini-Only Mode)
You can run the **entire application (both real-time voice conversations and post-session analysis/debriefing) using just a single Google Gemini API key**. This is the fastest, most cost-effective, and simplest configuration.

| Service | Purpose | Required/Optional | Link |
|--------|------|-----------|-----------|
| **Google (Gemini)** | Real-time Voice + Feedback Analysis | **Required (Single key setup)** | [aistudio.google.com](https://aistudio.google.com) |
| **Anthropic (Claude)** | Feedback Analysis (Alternative) | Optional (Gemini is default) | [console.anthropic.com](https://console.anthropic.com) |
| **OpenAI** | Real-time Voice + Feedback Analysis | Optional alternative | [platform.openai.com](https://platform.openai.com) |

### How to enter keys

Write your API keys to the `.env` file in the project directory using a text editor:

```
GEMINI_API_KEY=AIza...your_key_here...
ANTHROPIC_API_KEY=sk-ant-...your_key_here... (optional)
OPENAI_API_KEY=sk-...your_key_here... (optional)
```

Alternatively, you can enter them inside the application via **Tools → Preferences** (they will be automatically saved to your `.env` file).

---

## 2. Installation and Execution

### Method A: One-click installation & build via `build.bat` (Recommended)

1. Open the `MedVoiceTrainer` folder and double-click **`build.bat`**.
2. This will automatically install dependencies, run the test suite, and compile a standalone executable in `dist/MedVoiceTrainer/`.
3. Open `dist/MedVoiceTrainer/MedVoiceTrainer.exe` to launch the application.

> **Note:** The initial build may take 5 to 10 minutes depending on your internet connection.

### Method B: Run from source (Developer Mode)

Requires Python 3.11+.

```bat
cd MedVoiceTrainer
pip install -r requirements.txt
python main.py
```

### Dev Mode (Check UI without API keys or Microphone)

```bat
python main.py --dev
```

In `--dev` mode, the app uses preloaded mock transcripts and feedback to demonstrate all UI functionalities without calling any external APIs. A **[DEV MODE]** badge will be displayed at the bottom of the screen.

---

## 3. UI Layout Overview

The application features four primary tabs:

```
┌─────────────────────────────────────────────────────────┐
┌  Patient Encounter │ Residency Interview │ Custom │ History │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   [Case / Scenario Selector]                            │
│                                                         │
│   ▶ Pre-session Checklist (Click to expand)             │
│                                                         │
│   [Live Transcript Area]                                │
│   Patient (Blue background) / You (Green background)    │
│                                                         │
│  ● Start  ■ End & Analyze  ⏱ 00:00  🎤 Status           │
└─────────────────────────────────────────────────────────┘
```

### Menu Bar

| Menu | Action |
|------|------|
| **File → Export Anki** | Export Anki cards (`.apkg`) for selected sessions |
| **File → Export Docx** | Save docx feedback reports |
| **Tools → Preferences** | Set API keys, active backends, paths, auto-save settings |
| **View → Session History** | Show detailed attempt history |

---

## 4. Patient Encounters

### 4-1. Case Selection

* **System**: Clinical category (Foundations / Drills / Cardiology / GI / Pulm / Neuro).
* **Case**: The specific patient case and chief complaint.
* **Difficulty**: Case difficulty (Beginner / Intermediate / Advanced).

### 4-2. Pre-Session Checklist
Click **▶ Pre-session Checklist** to view list of history items or communication points you should cover. Starred (`*`) items are critical.

### 4-3. Session Flow
1. Click **● Start** to begin streaming.
2. Speak into your microphone in English to ask questions and take the history.
3. The AI patient responds in real-time, and transcriptions are shown on-screen.
4. When finished, say **"I'd like to summarize what we've discussed."** or click **■ End & Analyze**.

### 4-4. Self-Assessment
Upon finishing, you will see a self-assessment dialog. Grade your own performance from 0 to 10 on each metric, then click **Submit**. The app compares your grades to the AI's grades to evaluate self-awareness.

### 4-5. Feedback Loading
Analysis takes 10 to 30 seconds. Once completed, the Feedback Window opens automatically.

---

## 5. Residency Interviews

### 5-1. Category & Scenarios
* **Behavioral**: STAR method practice (Situation, Task, Action, Result).
* **Clinical**: Practice case presentations, clinical reasoning, and emergency communication.
* **IMG-Specific**: Practice explaining visa situations, clinical pathways, and cultural adaptability.

### 5-2. Interview Flow
The AI Program Director (PD) initiates the interview with an opening question. Respond via voice. The PD will probe further or ask follow-ups if your answers are vague.

---

## 6. Custom Scenarios

Configure custom role-play prompts and evaluation rubrics:
* **Scenario name**: Title of your scenario.
* **Persona / Context**: Complete prompt detailing the role the AI should play.
* **Eval template**: Pick a rubric template (e.g., SPIKES protocol).
* **Custom eval criteria**: Specify freeform custom rules for grading.
* Save scenarios to `data/custom/` or load them later.

---

## 7. Understanding the Feedback Window

Feedback is presented across 5 tabs:

### Tab 1: Scores
Visualizes your score alongside your self-assessment.
* **Grammar & Language**: Command of medical register and grammatical accuracy.
* **Medical Accuracy**: Correct medical terms and appropriate assessments.
* **Clinical Reasoning**: Differential diagnosis, prioritizing red flags, systematic workup.
* **Communication Fluency**: Natural delivery, signposting, minimum hesitation.

**Delta Interpretation:**
* `+ value`: Underestimated yourself (scored higher than you thought) — build confidence!
* `- value`: Overestimated yourself (scored lower than you thought) — focus on this area.

### Tab 2: Checklist
Lists the clinical checklist items:
* Green Check (✓ Pass): Covered in the session.
* Red Cross (✗ Fail): Missed item.
* Evidence column displays quotes from the transcript where the items were addressed.

### Tab 3: SOAP Note
Lists the AI-generated SOAP note based on your encounter side-by-side with the case's reference model SOAP note.

### Tab 4: Corrections
Direct language corrections for your turns:
* **Red Strikethrough**: What you said.
* **Green Text**: Better alternative phrasing.
* **Gray Italics**: Explanation / medical register tip.

### Tab 5: Summary
Overall strengths and weaknesses, alongside the number of generated Anki cards.

### 💬 Debrief with AI Tutor
Click **Debrief with AI Tutor** at the bottom of the feedback window to start a 1-on-1 Socratic discussion with a clinical mentor. The tutor asks guiding questions to help you reflect on your choices, instead of just telling you the answers.

---

## 8. Session History Management

Access your history via **View → Session History** or the **History** tab.
* **History Chart**: Plots performance trends over your last 10 attempts.
* **Comparison**: Retaking a case shows score differences compared to your previous attempt (e.g., `Grammar ▲0.8 | Reasoning ▼0.3`).

---

## 9. Exporting to Anki

Language corrections are automatically compiled into flashcards.
* Click **Export Anki** at the bottom of the Feedback Window, or select multiple sessions in the History tab and click **Export Anki** to compile them into an `.apkg` deck.
* Import the deck directly into the Anki desktop app (**File → Import**).

---

## 10. Saving Word Reports

Save a detailed session report:
* Click **Save Docx Report** to save manually.
* Check **Auto-save Docx** in Preferences to automatically save reports to a directory after each session.

---

## 11. Checking API Costs

A cost report text file is automatically generated for every session in:
`MedVoiceTrainer/db/cost_reports/cost_report_*.txt`

### 💡 Pricing Guide (5-min session):
* **Gemini-Only Mode (Recommended)**: **<$0.001** (fraction of a cent). Both voice and analysis run on Gemini, making it almost completely free.
* **Claude Analysis Mode**: **$0.02 - $0.05** (mostly driven by Claude input/output tokens).
* **OpenAI Realtime Mode**: **$0.10 - $0.20** per minute.

---

## 12. Preferences Configuration

Access preferences via **Tools → Preferences**:
* **Voice Backend**: Gemini Live or OpenAI Realtime.
* **Feedback AI**: Google Gemini, Anthropic Claude, or OpenAI.
* **API Keys**: Saved directly to your local `.env` file.
* **Docx export / Backup paths**: Folder locations.

---

## 13. FAQ

**Q: Microphone is not picking up audio.**
Check Windows Settings → Privacy & Security → Microphone access. Ensure your default microphone is selected and working.

**Q: Analysis fails.**
A **Retry Analysis** button will appear under the *End & Analyze* button. Click it to retry without losing your session transcript. Ensure your API keys are valid.

**Q: AI is answering in the wrong language.**
Speak clearly in English. Background noise can interfere with transcription. Gemini Live is pre-prompted in English and responds best to natural, flowing speech.

---

## 14. Scoring Rubric

All metrics are scored from 0 to 10:

* **9-10 (Excellent)**: Natural native-like phrasing, zero clinical errors, systematic structure, seamless transitions.
* **7-8 (Competent)**: Minor errors, fully comprehensible, appropriate medical register, safe reasoning.
* **5-6 (Developing)**: Structure needs improvement, some clinical gaps, noticeable hesitation, listener effort required.
* **1-4 (Critical)**: Frequent errors, incorrect terms, major safety or diagnostic issues, severe fluency blocks.

---

## 15. Case List

### 🌱 Foundations Mode
For junior pre-clinical students or early IMGs. Scored only on language and communication (no clinical reasoning checks). Focuses on building basic clinical English vocabulary and rapport. A **💬 Phrase Helper** panel is shown above the transcript with sample sentences.

* **found_001**: 3-day cold symptoms (Beginner)
* **found_002**: 2-week tension headache (Beginner)
* **found_003**: 1-month generalized fatigue (Beginner)

### 🎯 Skill Drills
Concentrated 3-4 turn exercises targeting specific communication skills:
* **drill_empathy**: NURSE protocol response practice.
* **drill_plain_language**: Explaining complex terms (biopsy, etc.) in lay terms.
* **drill_numbers**: Expressing doses, dates, spelling clearly.
* **drill_curveball**: Dealing with angry, silent, or crying patients.
* **drill_redirection**: Politely redirecting talkative patients back to the history.

### 🎯 Practice My Mistakes
Aggregates corrections from your history to generate an adaptive voice quiz. Re-evaluates your ability to produce correct clinical phrasing.

### 🏥 Clinical Cases (Patient Encounter)
* **cardio_001**: 2-hour acute chest pain (Intermediate)
* **cardio_002**: 3-week ankle edema & dyspnea (Beginner)
* **gi_001**: 2-day melena and dizziness (Intermediate)
* **gi_002**: 8-month diarrhea and abdominal pain (Advanced)
* **pulm_001**: 5-day COPD acute exacerbation (Intermediate)
* **pulm_002**: Haemoptysis (Advanced)
* **neuro_001**: Transient right arm weakness (Intermediate)
* **neuro_002**: Sudden onset "worst headache of life" (Advanced)
