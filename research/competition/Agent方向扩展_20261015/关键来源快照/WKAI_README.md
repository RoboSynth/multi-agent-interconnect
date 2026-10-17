# WKAI — Workshop AI

> A real-time AI-powered workshop assistance platform that silently monitors an instructor's screen, generates live step-by-step guides for students, and provides intelligent error diagnosis — built as a desktop-first application using Tauri, React, Node.js, and LangGraph.

---

## Team

| Name | USN |
|---|---|
| Mustafa Muhammad Abdulla | 4PA22CS092 |
| Mohammed Shammas I | 4PA23CS083 |
| Mohammed Zahid Ibrahim | 4PA23CS085 |
| Rafan Ahamad Sheik | 4PA23CS102 |

**Team Number:** 23CSMPB03

**Project Guide:** Prof. Habeeb Ur Rehman

**Project Coordinators:** Dr. Hafeez MK · Prof. Avvanhi

**Head of Department:** Dr. Sharmila Kumari M

---

## Abstract

WKAI (Workshop AI) addresses a core problem in live technical workshops: students struggle to keep pace with instructors, miss steps, and cannot get immediate help when they encounter errors. Traditional approaches — manual note-taking, static slides, human teaching assistants — do not scale.

WKAI is a three-component system. The instructor runs a lightweight desktop application (built with Tauri and Rust) that publishes low-latency WebRTC live video to students. A Node.js backend, powered by LangChain + LangGraph over Groq models (Llama-3 70B for text, Whisper Large v3 for audio), generates transcript-based explanations, quizzes, and coding assistance. These updates are delivered in real time via WebSocket to the student-facing React app. Students receive live instructor video, AI-generated learning guidance, error diagnosis support, and file sharing — without interrupting the instructor.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    wkai-backend (Node.js)                    │
│                                                             │
│   Express REST API              WebSocket Server            │
│   ├── POST /api/sessions        ws://host/ws               │
│   ├── GET  /api/sessions/:code  ├── instructor (1)          │
│   ├── POST /api/ai/transcribe   └── students   (n)          │
│   ├── POST /api/ai/diagnose                                  │
│   └── POST /api/run             AI Pipeline (Groq + LangGraph)│
│                                 ├── Screen Analysis          │
│   PostgreSQL                    ├── Error Diagnosis          │
│   └── 5 tables                  └── Intent Detection         │
│   Redis                                                      │
│   └── Session memory, transcripts, student counts           │
└─────────────────────────────────────────────────────────────┘
         ▲  HTTP + WebSocket                 ▲  HTTP + WebSocket
         │                                  │
┌────────┴───────────────┐     ┌────────────┴───────────────┐
│  wkai (Instructor)     │     │  wkai-student (Student)    │
│  Tauri Desktop App     │     │  React SPA (Browser)       │
│                        │     │                            │
│  Rust (src-tauri/)     │     │  JoinPage (6-char code)    │
│  ├── Screen capture    │     │  RoomPage                  │
│  ├── Audio capture     │     │  ├── GuideFeed             │
│  └── File watcher      │     │  ├── ComprehensionModal    │
│                        │     │  ├── FilesPanel            │
│  React (src/)          │     │  ├── CodeEditor (Monaco)   │
│  ├── SetupPage         │     │  └── ErrorHelper           │
│  ├── SessionPage        │     │                            │
│  └── SettingsPage      │     └────────────────────────────┘
└────────────────────────┘
```

---

## AI Agent Pipeline

WKAI uses LangGraph-based task agents and a centralized backend `Agents` layer (`VoiceAgent`, `QuizAgent`, `DebugAgent`, `IntentAgent`, `MessageAgent`) with per-agent feature flags, health checks, and metrics.

### Error Diagnosis Agent (LangGraph with retry loop)
```
classify → diagnose → parse → (retry up to 2x) → fallback
```
Student-pasted terminal errors are diagnosed by Llama-3 70B with structured parsing and retry. If AI is unavailable (quota/API issues), explicit availability status is returned.

### Intent Detection Agent (3 nodes)
```
heuristic_check → classify_intent → match_file
```
Each audio transcript is scanned for file-sharing intent ("share this file", "send the starter code"). If detected with sufficient confidence, the instructor receives a non-blocking toast asking whether to share the matched file.

---

## Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Instructor desktop | Tauri v2 (Rust + WebView) | 8–15 MB install, near-zero idle CPU, native screen/audio capture |
| Student web app | React 18 + TypeScript + Vite | Fast SPA, Monaco editor integration |
| Backend | Node.js (ESM) + Express + ws | Lightweight, same WebSocket protocol as Tauri |
| AI inference | Groq (300+ tok/s) | Realtime generation practical at workshop scale |
| LLM orchestration | LangChain + LangGraph | Retry loops, structured parsing, session memory |
| Audio transcription | Whisper Large v3 via Groq | 180× realtime; 30s chunk transcribed in under 200ms |
| Text / diagnosis | Llama-3 70B | Reasoning quality for error diagnosis |
| Session memory | Redis (LangChain history) | Rolling 20-message context survives restarts |
| Persistent storage | PostgreSQL | Guide blocks, files, error logs |
| File storage | Cloudinary | Free 25 GB tier; direct student download URLs |
| State management | Zustand | Minimal boilerplate, no Provider wrapping |
| Output validation | Zod | Runtime schema enforcement for LLM JSON |

---

## Repository Structure

```
wkai/                 Instructor desktop app    Tauri v2 + Rust + React + TypeScript
wkai-backend/         Backend server            Node.js + WebSocket + PostgreSQL + Redis
wkai-student/         Student web app           React + TypeScript + Vite
```

---

## Key Features

- **Zero-effort guide generation** — instructor teaches normally; WKAI watches and generates
- **Comprehension gating** — students must answer a question correctly before content unlocks
- **Error diagnosis** — paste any terminal error; get a diagnosis and fix command in seconds
- **WebRTC live delivery** — low-latency instructor-to-student video stream with adaptive browser quality
- **Sandboxed code execution** — run Python, JavaScript, TypeScript, Bash directly in the browser
- **File sharing** — instructor shares files with one tap; students download instantly
- **Intent-aware audio** — AI detects "share this file" in speech and prompts the instructor
- **Session memory** — AI remembers what was taught earlier in the workshop
- **Centralized AI agents** — uniform agent lifecycle (`name/version/invoke/healthCheck`) for easier future updates
- **System tray** — instructor app runs silently; does not interrupt the teaching flow

---

## Prerequisites

```
Node.js >= 20
Rust + cargo (via rustup)
Docker Desktop
Groq API key      → https://console.groq.com  (free, no card required)
Cloudinary account → https://cloudinary.com    (free 25 GB tier)
```

---

## Getting Started

### Step 1 — Clone and install

```bash
git clone <repo-url>
cd wkai

# Install all three repos
cd wkai-backend && npm install && cd ..
cd wkai-student && npm install && cd ..
cd wkai && npm install && cd ..
```

### Step 2 — Configure environment

```bash
cd wkai-backend
cp .env.example .env
# Edit .env — fill in GROQ_API_KEY, CLOUDINARY_* values
```

### Step 3 — Start databases

```bash
cd wkai-backend
docker compose up -d
npm run db:migrate   # first time only
```

### Step 4 — Start servers

```bash
# Terminal 1 — Backend
cd wkai-backend && npm run dev

# Terminal 2 — Student web app
cd wkai-student && npm run dev

# Terminal 3 (Windows PowerShell) — Instructor desktop app
cd wkai && npm run tauri:dev
```

### Step 5 — Start a session

1. Open the instructor desktop app
2. Enter your name and workshop title, then click **Start Session**
3. Share the 6-character room code with students
4. Students open `http://localhost:3000` and enter the code
5. Teach — WKAI handles the rest

---

## Environment Variables

| Variable | Required | Source |
|---|---|---|
| `GROQ_API_KEY` | Yes | console.groq.com |
| `DATABASE_URL` | Yes | Pre-filled for local Docker |
| `REDIS_URL` | Yes | Pre-filled for local Docker |
| `CLOUDINARY_CLOUD_NAME` | Yes | cloudinary.com dashboard |
| `CLOUDINARY_API_KEY` | Yes | cloudinary.com dashboard |
| `CLOUDINARY_API_SECRET` | Yes | cloudinary.com dashboard |
| `AI_AGENT_VOICE_AGENT_ENABLED` | No | Agent feature flag (`true`/`false`) |
| `AI_AGENT_QUIZ_AGENT_ENABLED` | No | Agent feature flag (`true`/`false`) |
| `AI_AGENT_DEBUG_AGENT_ENABLED` | No | Agent feature flag (`true`/`false`) |
| `AI_AGENT_INTENT_AGENT_ENABLED` | No | Agent feature flag (`true`/`false`) |
| `AI_AGENT_MESSAGE_AGENT_ENABLED` | No | Agent feature flag (`true`/`false`) |
| `STUDENT_JOIN_TOKEN_SECRET` | Yes (prod) | Random secret for signed student join tokens |
| `CORS_ALLOWED_ORIGINS` | Yes (prod) | Comma-separated allowed origins (landing/student domains) |

---

## Additional Docs

- Full implementation history: `changelog.md`
- Backend architecture and API details: `wkai-backend/README.md`
- Render deployment spec: `render.yaml`

---

## Deployment Runbook

### Backend on Render
1. Create a Render service from this repo using `render.yaml`.
2. Configure required variables: `DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY`, `STUDENT_JOIN_TOKEN_SECRET`, `CORS_ALLOWED_ORIGINS`.
3. Ensure `CORS_ALLOWED_ORIGINS` includes your Vercel domains.
4. Verify service health at `GET /health`.

### Landing + Student Web on Vercel
1. Deploy `wkai-student` to Vercel (SPA rewrite is in `wkai-student/vercel.json`).
2. Set `VITE_BACKEND_URL`, `VITE_GITHUB_REPO_OWNER`, `VITE_GITHUB_REPO_NAME`.
3. Validate routes:
   - `/` landing
   - `/download` release downloader
   - `/join` student join form

### CI/CD Version Bump
1. Push changes to `main`.
2. `Bump And Tag Release` auto-increments patch version and creates a new `vX.Y.Z` tag.
3. `Release` workflow builds and publishes desktop artifacts for the new tag.

---

## Research Papers

This project draws on the following published research:

| # | Title | Year | Venue | Link |
|---|---|---|---|---|
| 1 | A Comprehensive Review of AI-based Intelligent Tutoring Systems: Applications and Challenges | 2025 | ArXiv | [Link to be added] |
| 2 | Ruffle & Riley: Insights from Designing and Evaluating a Large Language Model-Based Conversational Tutoring System | 2024 | AIED 2024 Workshop | [Link to be added] |
| 3 | Tutor CoPilot: A Human-AI Approach for Scaling Real-Time Expertise | 2024 | NSSA Technical Report (Stanford) | [Link to be added] |
| 4 | ScreenAI: A Vision-Language Model for UI and Infographics Understanding | 2024 | IJCAI 2024 | [Link to be added] |
| 5 | MultiTutor: Collaborative LLM Agents for Multimodal Student Support | 2025 | AI-Supported Education (PMLR) | [Link to be added] |
| 6 | MMTutorBench: The First Multimodal Benchmark for AI Math Tutoring | 2025 | ArXiv | [Link to be added] |
| 7 | Video-MMLU: A Massive Multi-Discipline Lecture Understanding Benchmark | 2025 | ArXiv / CVPR | [Link to be added] |
| 8 | MathBuddy: A Multimodal System for Affective Math Tutoring | 2025 | EMNLP 2025 Demo | [Link to be added] |
| 9 | LeafTutor: An AI Agent for Programming Assignment Tutoring | 2026 | ArXiv | [Link to be added] |

---

## Acknowledgements

We thank **Prof. Habeeb Ur Rehman** for guidance throughout the project, and **Dr. Hafeez MK** and **Prof. Avvanhi** for coordinating the project phase. We also acknowledge the open-source communities behind Tauri, LangChain, LangGraph, and Groq whose work made this system possible.

---

## License

This project is submitted as part of the academic curriculum of the Department of Computer Science and Engineering. All rights reserved by the respective authors.
