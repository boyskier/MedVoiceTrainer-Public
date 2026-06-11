# MedVoiceTrainer 사용 설명서

**대상:** OSCE, OET, 미국 내과 레지던시 매치를 준비하는 한국 의대생 / IMG

---

## 목차

1. [시작하기 전에 — API 키 발급](#1-시작하기-전에--api-키-발급)
2. [설치 및 실행](#2-설치-및-실행)
3. [화면 구성 한눈에 보기](#3-화면-구성-한눈에-보기)
4. [환자 진료 연습 (Patient Encounter)](#4-환자-진료-연습-patient-encounter)
5. [레지던시 인터뷰 연습 (Residency Interview)](#5-레지던시-인터뷰-연습-residency-interview)
6. [자유 시나리오 연습 (Custom Scenario)](#6-자유-시나리오-연습-custom-scenario)
7. [피드백 창 읽는 법](#7-피드백-창-읽는-법)
8. [세션 기록 관리 (Session History)](#8-세션-기록-관리-session-history)
9. [Anki 카드 내보내기](#9-anki-카드-내보내기)
10. [Word 보고서 저장](#10-word-보고서-저장)
11. [API 비용 확인](#11-api-비용-확인)
12. [환경 설정 (Preferences)](#12-환경-설정-preferences)
13. [자주 묻는 질문 (FAQ)](#13-자주-묻는-질문-faq)
14. [점수 기준표](#14-점수-기준표)
15. [케이스 목록](#15-케이스-목록)

---

## 1. 시작하기 전에 — API 키 발급

MedVoiceTrainer는 구글 제미나이(Google Gemini), 앤트로픽 클로드(Anthropic Claude), 오픈AI(OpenAI)를 지원합니다.

### 💡 권장 설정 (제미나이 단일 키로 모든 기능 사용)
이제 **Google Gemini API 키 하나만 있으면 실시간 음성 대화와 피드백 분석(AI 튜터 포함)까지 모두 사용**할 수 있습니다. 가장 빠르고 비용 효율적이며 설정이 간단합니다.

| 서비스 | 용도 | 권장/필수 | 발급 링크 |
|--------|------|-----------|-----------|
| **Google (Gemini)** | 실시간 음성 대화 + 피드백 분석 | **필수 (단일 키로 작동 가능)** | [aistudio.google.com](https://aistudio.google.com) |
| **Anthropic (Claude)** | 피드백 분석 (선택 변경 가능) | 선택 사항 (Gemini로 대체 가능) | [console.anthropic.com](https://console.anthropic.com) |
| **OpenAI** | 실시간 음성 대화 + 피드백 분석 | 선택 사항 | [platform.openai.com](https://platform.openai.com) |

### 키 입력 방법

발급받은 키를 프로그램 폴더 안의 `.env` 파일에 입력합니다. 메모장으로 열어서 아래와 같이 작성하세요:

```
GEMINI_API_KEY=AIza...여기에_발급받은_키_붙여넣기...
ANTHROPIC_API_KEY=sk-ant-...여기에_발급받은_키_붙여넣기... (선택)
OPENAI_API_KEY=sk-...여기에_발급받은_키_붙여넣기... (선택)
```

또는 프로그램 실행 후 **Tools → Preferences** 에서 입력할 수 있습니다. (기본 피드백 엔진은 Gemini로 기본 설정되어 있으므로, 제미나이 키만 입력하시면 바로 모든 기능을 사용할 수 있습니다.)

---

## 2. 설치 및 실행

### 방법 A: build.bat으로 한 번에 설치 + 실행파일 생성 (권장)

1. `MedVoiceTrainer` 폴더를 열고 **`build.bat`** 를 더블클릭합니다.
2. 자동으로 필요한 패키지가 설치되고 `dist/MedVoiceTrainer/` 폴더에 실행파일이 생성됩니다.
3. `dist/MedVoiceTrainer/MedVoiceTrainer.exe` 를 더블클릭하면 실행됩니다.

> **처음 빌드는 5~10분 정도 걸릴 수 있습니다.**

### 방법 B: Python으로 직접 실행 (개발자 모드)

Python 3.11 이상이 설치되어 있어야 합니다.

```bat
cd MedVoiceTrainer
pip install -r requirements.txt
python main.py
```

### 개발/테스트 모드 (API 키 없이 UI 확인)

```bat
python main.py --dev
```

`--dev` 플래그를 사용하면 실제 API 연결 없이 미리 입력된 대화와 피드백으로
프로그램의 모든 기능을 체험할 수 있습니다. 화면 하단에 **[DEV MODE]** 배지가 표시됩니다.

---

## 3. 화면 구성 한눈에 보기

프로그램을 실행하면 네 개의 탭이 있습니다:

```
┌─────────────────────────────────────────────────────────┐
│  Patient Encounter │ Residency Interview │ Custom │ History │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   [케이스 선택 영역]                                    │
│                                                         │
│   ▶ Pre-session Checklist (클릭해서 펼치기)             │
│                                                         │
│   [대화 기록 영역]                                      │
│   환자(파란 배경) / 나(초록 배경)                       │
│                                                         │
│  ● Start  ■ End & Analyze  ⏱ 00:00  🎤 상태           │
└─────────────────────────────────────────────────────────┘
```

### 상단 메뉴

| 메뉴 | 기능 |
|------|------|
| **File → Export Anki** | 선택한 세션의 Anki 카드를 .apkg 파일로 저장 |
| **File → Export Docx** | 선택한 세션의 Word 보고서를 저장 |
| **Tools → Preferences** | API 키, 음성 백엔드, 저장 폴더 설정 |
| **View → Session History** | 이전 세션 기록 보기 |

---

## 4. 환자 진료 연습 (Patient Encounter)

### 4-1. 케이스 선택

| 항목 | 설명 |
|------|------|
| **System** | 진료과 선택 (Cardio / GI / Pulm / Neuro) |
| **Case** | 케이스 선택 (환자 ID와 주증상 표시) |
| **Difficulty** | 난이도 필터 (Beginner / Intermediate / Advanced) |

### 4-2. 세션 시작 전

**▶ Pre-session Checklist** 버튼을 클릭하면 이번 케이스에서 물어봐야 할
항목 목록이 나타납니다. `*` 표시가 있는 항목은 필수입니다.

> 예: onset and duration *, character and severity *, ICE explored *

### 4-3. 세션 진행

1. **● Start** 버튼을 클릭합니다.
2. 마이크에 대고 영어로 병력청취를 시작합니다.
3. 화면에 대화 내용이 실시간으로 표시됩니다:
   - **파란 배경** = 환자의 발언
   - **초록 배경** = 내 발언
4. 세션을 끝내려면 **"I'd like to summarize what we've discussed."** 라고 말하거나
   **■ End & Analyze** 버튼을 누릅니다.

### 4-4. 자기 평가 (Self-Assessment)

세션이 끝나면 자기 평가 창이 먼저 나타납니다.
슬라이더로 각 항목을 0~10점으로 평가한 후 **Submit** 을 클릭하세요.

> AI의 점수와 내 자기평가 점수를 비교해서 self-awareness를 체크할 수 있습니다.

### 4-5. 분석 대기

분석은 보통 **10~30초** 정도 걸립니다. 완료되면 피드백 창이 자동으로 열립니다.

---

## 5. 레지던시 인터뷰 연습 (Residency Interview)

### 5-1. 시나리오 선택

| 항목 | 설명 |
|------|------|
| **Category** | Behavioral / Clinical / IMG-Specific |
| **Scenario** | 시나리오 선택 (PD 이름과 첫 질문 표시) |

상단 정보 바에 **PD 이름**과 **프로그램명**이 표시됩니다.

### 5-2. 카테고리별 특징

**Behavioral (행동 면접)**
- STAR 형식으로 답변하세요: Situation → Task → Action → Result
- 막연한 답변보다 구체적인 경험을 이야기하세요
- 예: "When I was working at XXX Hospital in 2023..."

**Clinical (임상 면접)**
- 실제 증례를 바탕으로 임상적 추론 과정을 설명하세요
- 감별진단을 언급하고 위험한 진단을 먼저 배제하는 구조로 답하세요

**IMG-Specific (외국 의대 출신 특화)**
- 비자 상황, 적응 전략, 갭이어 설명 등을 준비하세요
- 자신의 국제적 배경을 강점으로 프레이밍하는 연습을 하세요

### 5-3. 인터뷰 진행

AI PD가 먼저 질문합니다. 마이크에 대고 답변하세요.
AI는 답변이 모호하면 follow-up 질문을 합니다.

---

## 6. 자유 시나리오 연습 (Custom Scenario)

원하는 상황을 직접 설정해서 연습할 수 있습니다.

### 6-1. 설정 항목

| 항목 | 설명 | 예시 |
|------|------|------|
| **Scenario name** | 시나리오 이름 | "SPIKES_practice_01" |
| **Persona / context** | AI가 연기할 역할과 상황 설명 | 아래 예시 참고 |
| **Eval template** | 평가 기준 템플릿 선택 | spikes_bad_news |
| **Custom eval criteria** | 직접 평가 기준 작성 (자유 서술) | "SPIKES 6단계를 지켰는지..." |

### 6-2. Persona 작성 예시

```
You are Mrs. Kim, a 52-year-old Korean-American woman who has just been told 
her biopsy results are ready. She is anxious and has her daughter with her. 
She uses simple English but understands medical terms if explained clearly.
Session ends when the student says "I'd like to end the session."
```

### 6-3. 시나리오 저장/불러오기

- **Save as JSON**: 작성한 시나리오를 `data/custom/` 폴더에 저장합니다
- **Load saved scenario**: 저장된 시나리오를 불러옵니다

---

## 7. 피드백 창 읽는 법

세션 분석 후 피드백 창이 5개 탭으로 나타납니다.

### 탭 1: Scores (점수)

각 항목의 AI 점수와 자기평가 점수가 막대 그래프로 표시됩니다.

| 항목 | 설명 |
|------|------|
| **Grammar & Language** | 문법 정확도, 의료 레지스터 적절성 |
| **Medical Accuracy** | 의학 용어 및 임상 정보의 정확성 |
| **Clinical Reasoning** | 감별진단, 위험 진단 우선 고려, 체계적 접근 |
| **Communication Fluency** | 자연스러운 전달, 망설임 최소화, 신호어 사용 |

**Delta 해석:**
- `+숫자` = 내가 스스로를 낮게 평가함 (실제보다 더 잘함) → 자신감 UP
- `-숫자` = 내가 스스로를 높게 평가함 (생각보다 못함) → 더 연습 필요

### 탭 2: Checklist (체크리스트)

| 표시 | 의미 |
|------|------|
| ✓ Pass (초록) | 해당 항목을 물어봄 |
| ✗ Fail (빨강) | 해당 항목을 놓침 |

Evidence 열에 실제 대화에서 찾은 근거 문장이 표시됩니다.

### 탭 3: SOAP Note

| 영역 | 내용 |
|------|------|
| **좌측** | AI가 분석한 내 SOAP 노트 |
| **우측** | 참고 답안 SOAP (케이스 파일의 모범 답안) |

두 SOAP을 비교해서 내가 놓친 clinical point를 확인하세요.

### 탭 4: Corrections (언어 교정)

각 교정 항목에는:
- **빨간 글씨**: 내가 실제로 한 말
- **초록 글씨**: 더 나은 표현
- **회색 기울임**: 교정 이유 설명

> 예:
> ~~"Can you tell me about the pain?"~~
> → **"Could you describe the pain for me?"**
> *더 개방적인 질문이 환자의 풍부한 서술을 유도합니다.*

### 탭 5: Summary (종합 피드백)

전체적인 강점과 개선점을 서술 형식으로 제공합니다.
Anki 카드가 몇 장 생성되었는지도 표시됩니다.

### 💬 AI 튜터와 디버깅 (Debrief with AI Tutor)

피드백 창 하단의 **Debrief with AI Tutor** 버튼을 클릭하면, 학습 전용 AI 지도 교수와 1:1 대화(Socratic debriefing)를 나눌 수 있는 새 대화 창이 열립니다.
* **소크라테스식 대화**: 일방적인 주입식 피드백이 아닌, 대화 속에서 내 진료/인터뷰 흐름을 돌아볼 수 있도록 유도 질문을 던져 학습 효율을 높여 줍니다.
* **설정 AI 연동**: 환경설정에서 선택한 피드백 AI 백엔드(Claude, Gemini, OpenAI)를 사용해 구동됩니다. (예: Gemini를 피드백 AI로 선택 시 Gemini API를 통해 동작)
* **대화 내역 보존**: 진행했던 디버깅 대화 내용은 세션별로 보존되어 언제든지 다시 이어서 대화할 수 있습니다.

---

## 8. 세션 기록 관리 (Session History)

**View → Session History** 또는 History 탭에서 모든 이전 세션을 볼 수 있습니다.

### 비교 기능

같은 케이스를 여러 번 연습하면, 선택 시 상단에 이전 점수와의 비교가 표시됩니다:

```
vs. your last attempt: Grammar ▲0.8 | Accuracy ▲1.2 | Reasoning ▼0.3 | Fluency ▲0.5
```

▲ = 향상, ▼ = 하락

### 점수 추이 차트

최근 10개 세션의 4가지 점수를 꺾은선 그래프로 확인할 수 있습니다.
꾸준히 연습하면 그래프가 우상향하는 것을 볼 수 있습니다.

### 세션 삭제

목록에서 선택 후 **Delete** 버튼을 누르면 삭제됩니다.
**삭제한 세션은 복구할 수 없으니 주의하세요.**

---

## 9. Anki 카드 내보내기

세션마다 언어 교정과 유용한 임상 표현이 Anki 카드로 자동 생성됩니다.

### 내보내기 방법

**방법 1 — 피드백 창에서:**
1. 피드백 창 하단의 **Export Anki** 버튼 클릭
2. 저장 위치 선택 → `.apkg` 파일 저장

**방법 2 — History 탭에서 (여러 세션 한꺼번에):**
1. History 탭에서 원하는 세션을 Ctrl+클릭으로 여러 개 선택
2. **Export Anki** 버튼 클릭

### Anki에서 불러오기

1. Anki 앱 실행
2. **파일 → 가져오기** (Import)
3. 저장한 `.apkg` 파일 선택
4. **MedVoiceTrainer** 덱에 카드가 추가됩니다

---

## 10. Word 보고서 저장

각 세션의 피드백을 Word 문서로 저장할 수 있습니다.

### 수동 저장

피드백 창 하단의 **Save Docx Report** 버튼 클릭

### 자동 저장 설정

**Tools → Preferences** → **Auto-save Docx** 체크박스를 켜고
저장 폴더를 지정하면, 세션이 끝날 때마다 자동으로 저장됩니다.

### 파일명 형식

```
20260602_encounter_Mr_Johnson.docx
(날짜_모드_환자이름.docx)
```

---

## 11. API 비용 확인

세션이 끝나면 자동으로 비용 보고서가 생성됩니다.

### 보고서 위치

```
MedVoiceTrainer/
└── db/
    └── cost_reports/
        └── cost_report_42_20260602_103015.txt
```

### 보고서 내용 예시

```
========================================================
  MedVoiceTrainer — Session API Cost Report
========================================================
  Session ID: 42
  Duration  : 5m 0s
  Backend   : gemini

── Claude API (Post-Session Analysis) ──────────────────
  Input tokens     : 3,200
  Output tokens    : 850
  Cost             : $0.022550

── Gemini Live (Voice Session) ─────────────────────────
  Audio seconds    : 300s
  Cost (estimated) : $0.000480

── Total ────────────────────────────────────────────────
  TOTAL COST (USD) : $0.023030
========================================================
```

> **💡 비용 안내 (5분 세션 기준):**
> - **Google Gemini 단일 사용 시 (권장)**: 총 비용 약 **$0.001 미만** (약 1.5원). 피드백과 음성 모두 Gemini를 사용하여 비용이 거의 발생하지 않습니다.
> - **Claude 피드백 분석 사용 시**: 총 비용 약 **$0.02~0.05** (약 30~70원). Claude API 분석 비용이 대부분을 차지합니다.
> - **OpenAI Realtime 음성 사용 시**: 분당 약 $0.10~0.20 수준으로 비용이 다소 높은 편입니다.

---

## 12. 환경 설정 (Preferences)

**Tools → Preferences** 메뉴에서 접근합니다.

| 설정 | 설명 |
|------|------|
| **Voice Backend** | 음성 AI 선택 (Gemini Live / OpenAI Realtime) |
| **Feedback AI (post-session analysis)** | 피드백 분석 및 AI 튜터 디버깅에 사용할 AI 모델 선택 (Claude, Gemini, OpenAI) |
| **Gemini API Key** | Gemini 음성/피드백용 API 키 입력 |
| **Anthropic API Key** | Claude 피드백용 API 키 입력 |
| **OpenAI API Key** | OpenAI 음성/피드백용 API 키 입력 |
| **Docx export folder** | Word 파일 저장 폴더 |
| **Auto-save Docx** | 세션 종료 시 자동 저장 여부 |
| **Backup folder** | DB 백업 저장 위치 |

> **API 키 저장:** Preferences 창에서 입력한 API 키는 자동으로 프로그램 폴더 안의 `.env` 파일에 저장되므로, 매번 다시 입력하실 필요가 없습니다.

---

## 13. 자주 묻는 질문 (FAQ)

**Q: 마이크가 인식되지 않습니다.**
A: 화면 하단 상태 표시줄에 오류 메시지가 표시됩니다. Windows 설정 → 개인 정보 → 마이크 접근 권한을 확인하세요. 또한 기본 마이크 장치가 올바르게 설정되어 있는지 확인하세요.

**Q: 분석이 실패했다고 나옵니다.**
A: `■ End & Analyze` 버튼 아래에 **Retry Analysis** 버튼이 나타납니다. 클릭하면 대화 내용은 유지된 채로 분석을 다시 시도합니다. 여러 번 실패하면 ANTHROPIC_API_KEY가 올바른지 확인하세요.

**Q: 음성이 인식되지 않거나 한국어로 대답합니다.**
A: 마이크에 가까이 대고 영어로 말하세요. 배경 소음이 크면 인식률이 떨어집니다. Gemini는 영어 명령어로 설정되어 있으므로 영어로 말해야 합니다.

**Q: 프로그램이 응답하지 않습니다.**
A: 분석 중에는 잠시 기다려 주세요. 30초 이상 응답이 없으면 프로그램을 재시작하세요. 대화 내용은 DB에 저장되어 있으므로 History 탭에서 확인할 수 있습니다.

**Q: 새로운 케이스를 추가하고 싶습니다.**
A: `data/cases/` 폴더 안의 적절한 하위 폴더에 JSON 파일을 추가하세요. 기존 케이스 파일을 참고해서 같은 형식으로 작성하면 됩니다. 프로그램을 재시작하면 자동으로 목록에 나타납니다.

**Q: 영어 자막(transcript)이 정확하지 않습니다.**
A: 음성 인식 품질은 마이크 품질과 발화 명확성에 따라 달라집니다. 천천히 또렷하게 발음하면 인식률이 크게 향상됩니다. OpenAI Realtime은 Gemini보다 영어 인식 정확도가 높은 편입니다.

**Q: 세션을 실수로 삭제했습니다.**
A: `db/backups/` 폴더에 자동 백업이 있습니다. 최신 백업 파일(`sessions_날짜_시간.db`)을 `db/sessions.db`로 복사하면 복구됩니다.

---

## 14. 점수 기준표

모든 항목은 **0~10점** 으로 평가됩니다.

### Grammar & Language (문법/언어)

| 점수 | 기준 |
|------|------|
| 9-10 | 오류 없음. 원어민 수준의 의학적 표현. |
| 7-8 | 간간이 작은 오류. 충분히 이해 가능. 적절한 레지스터. |
| 5-6 | 어느 정도의 구조적 오류. 청자의 노력 필요. |
| 3-4 | 잦은 오류. 간혹 이해 어려움. |
| 1-2 | 매우 잦은 오류. 의사소통 심각히 저하. |

### Medical Accuracy (의학적 정확성)

| 점수 | 기준 |
|------|------|
| 9-10 | 모든 의학 용어 및 임상 정보 정확. |
| 7-8 | 경미한 부정확함. 위험한 오류 없음. |
| 5-6 | 일부 용어 오류 또는 임상 추론 오류. |
| 3-4 | 다수의 임상 오류. |
| 1-2 | 심각한 위험 오류 포함. |

### Clinical Reasoning (임상 추론)

| 점수 | 기준 |
|------|------|
| 9-10 | 감별진단 명확히 언급. 위험 진단 우선 배제. 체계적 접근. |
| 7-8 | 합리적인 감별진단. 주요 위험 인자 탐색. |
| 5-6 | 어느 정도 구조화된 접근이나 중요 항목 누락. |
| 3-4 | 비체계적 질문. 감별진단 없음. |
| 1-2 | 임상 추론의 증거 없음. |

### Communication Fluency (의사소통 유창성)

| 점수 | 기준 |
|------|------|
| 9-10 | 자연스럽고 유창한 전달. 적절한 신호어. 망설임 없음. |
| 7-8 | 간간이 망설임. 대체로 매끄러운 전환. |
| 5-6 | 눈에 띄는 망설임 또는 어색한 표현. |
| 3-4 | 잦은 멈춤. 의사소통 방해. |
| 1-2 | 유창성 문제로 의사소통 심각히 저하. |

---

## 15. 케이스 목록

### 🌱 기초 (Foundations) — 본과 저학년 / 실습 전 IMG용

> **이 모드부터 시작하세요.** 임상실습을 아직 돌지 않은 학생을 위한 모드입니다.
> 감별진단·임상추론을 채점하지 **않고**, 오직 **의학 영어 어휘·발음·소통**만 평가합니다.
> 환자가 더 천천히·친절하게 말하고, 학생이 막히면 살짝 힌트를 줍니다 (coaching mode).
> System 드롭다운에서 **foundations** 를 선택하세요.

| 케이스 ID | 상황 | 난이도 | 연습 목표 |
|-----------|------|--------|-----------|
| found_001 | 3일째 콧물·인후통 (감기) | Beginner | 인사·자기소개, 개방형 질문, 기본 증상 어휘 |
| found_002 | 2주간 오후 두통 | Beginner | 통증을 쉬운 말로 묘사, 공감 표현, 안심시키기 |
| found_003 | 한 달째 피로감 | Beginner | 생활습관·수면 대화, 쉬운 조언, 공감 |

> **Foundations 모드의 점수 항목** (0~10점): Grammar & Sentences(문장),
> Medical Vocabulary(어휘), Communication & Rapport(소통·라포),
> Fluency & Pronunciation(유창성·발음). SOAP 노트는 평가하지 않습니다.

> **💬 Phrase Helper (예시 발문 도우미):** Foundations 케이스를 선택하면 대화 영역 위에
> 초록색 **💬 Phrase Helper** 패널이 자동으로 펼쳐집니다. 인사·개방형 질문·증상 묻기·공감·
> 마무리 등 단계별 예시 문장과, **이 환자에게 바로 물어볼 수 있는 추천 질문(★)** 이 들어 있습니다.
> 처음엔 한 줄을 그대로 소리내어 읽고, 익숙해지면 자기 말로 바꿔 보세요. 제목을 클릭하면 접을 수 있습니다.

### 🎯 스킬 드릴 (Skill Drills) — 음성 AI로만 가능한 집중 훈련

> Patient Encounter 탭의 **System 드롭다운에서 `drills`** 를 선택하세요.
> 전체 병력청취가 아니라, **한 가지 소통 스킬만 짧은 turn으로 반복** 훈련합니다.
> AI가 매 turn 하나의 과제를 던지므로 완전 초보도 부담 없이 시작할 수 있고,
> Phrase Helper에는 그 드릴 전용 예시 표현이 표시됩니다.

| 드릴 ID | 훈련 내용 | 이 프로그램만의 강점 |
|---------|-----------|----------------------|
| drill_empathy | **공감 반응(NURSE)** — AI 환자가 불안·슬픔·좌절을 표현하면 즉각 공감 문장으로 응답 | 감정을 연기하는 AI 상대로 반복 연습 |
| drill_plain_language | **쉬운 말 설명** — hypertension·biopsy 등 전문용어를 환자에게 plain English로 풀어 설명 | 환자가 "아직 모르겠어요"라고 되물으며 압박 |
| drill_numbers | **숫자·용량·철자 말하기** — 혈압·용량·날짜·이름 철자를 자연스러운 영어로 소리내 말하기 | 음성 입력으로 발음·명료도까지 평가 |
| drill_curveball | **돌발 상황 대처** — 환자가 갑자기 울거나·화내거나·침묵하거나·민감한 말을 던질 때 침착하게 대응 | 대본으로 불가, 매번 다르게 반응하는 AI라야 가능 |
| drill_redirection | **산만한 환자 redirection** — 자꾸 옆길로 새는 수다스러운 환자를 정중히 본론으로 | 반응형 파트너로 대화 주도권·시간 관리 연습 |

> 각 드릴은 임상추론을 채점하지 않고 해당 스킬에 맞춘 4개 항목으로 평가합니다
> (예: 공감 드릴은 *Empathy & Acknowledgement* 가 핵심 점수).

### 🎯 내 실수 복습 (Practice My Mistakes) — 내 기록 기반 개인 맞춤

> Patient Encounter 탭 상단의 **🎯 My Mistakes** 버튼을 누르세요.
> 앱이 **내 과거 세션들의 교정(corrections)을 모아 자주 틀린 표현 6개**를 골라냅니다.
> 그러면 AI 코치가 그 표현을 *말로 다시 만들어내야 하는* 새 상황을 즉석에서 던집니다 —
> **정답을 먼저 알려주지 않고**, 내가 개선된 표현을 스스로 발화하도록 유도합니다.
> Phrase Helper에는 내 목표 표현들이 표시되고, 세션 후 분석은 각 표현을 제대로 썼는지 항목별로 채점합니다.
>
> *처음 사용 시* 모을 교정이 부족하면(3개 미만) "먼저 몇 세션을 해보라"는 안내가 뜹니다.
> 즉, **일반 연습 → 약점 누적 → 그 약점만 음성으로 재훈련** 의 닫힌 루프입니다.

### 내과 (Patient Encounter)

| 케이스 ID | 주증상 | 난이도 | 주요 학습 목표 |
|-----------|--------|--------|----------------|
| cardio_001 | 흉통 2시간 | Intermediate | ACS 병력청취, ICE 탐색, 심혈관 위험인자 |
| cardio_002 | 양측 발목 부종, 호흡곤란 3주 | Beginner | 심부전 악화 원인 탐색, 약물 순응도 |
| gi_001 | 흑변 2일, 현기증 | Intermediate | 상부 위장관 출혈, NSAID 연관성 |
| gi_002 | 복통 및 설사 8개월 | Advanced | IBD vs IBS, 적신호 증상, 암 불안 상담 |
| pulm_001 | 호흡곤란 악화, 화농성 객담 5일 | Intermediate | COPD 급성 악화, 항생제 적응증 |
| pulm_002 | 객혈 2회 | Advanced | 폐결핵 의심, 공중보건 신고, 문화적 감수성 |
| neuro_001 | 일시적 우측 팔 마비 및 발음 장애 | Intermediate | TIA 인식, ABCD2 점수, 뇌졸중 예방 교육 |
| neuro_002 | 갑자기 발생한 '일생 최악의 두통' | Advanced | 지주막하출혈 응급, 뇌척수액 검사 필요성 설명 |

### 레지던시 인터뷰

| ID | 카테고리 | 첫 질문 |
|----|----------|---------|
| behavioral_001~005 | Behavioral | 자기소개, 실수 경험, 어려운 환자, 진로 목표 등 |
| img_001~003 | IMG-Specific | 의학교육 경로, 미국 적응 전략, 갭이어 설명 등 |
| clinical_001~003 | Clinical | 복잡한 증례 발표, 급성 악화 대응, 윤리적 딜레마 등 |

---

*MedVoiceTrainer | 버전 1.0 | 2026*

*이 프로그램은 연습 도구입니다. 실제 임상 판단의 대체재가 아닙니다.*
