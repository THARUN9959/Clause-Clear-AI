# ClauseClear AI — Build Walkthrough

## What Was Built

A full-stack Generative AI web application for legal contract simplification, powered by Gemini 2.5 Flash Lite with context engineering best practices.

## Architecture

```mermaid
graph TB
    subgraph Frontend
        A[index.html - Landing] --> B[analyze.html - Workspace]
        A --> C[history.html - DB Viewer]
    end
    subgraph Backend
        D[app.py - Flask Routes]
        E[gemini_service.py - Unified/Legacy Prompts & RAG]
        F[playbooks.py - Indian Legal Standards]
        G[document_service.py - PDF/OCR/DOCX Parser]
        H[database.py - SQLModel CRUD]
    end
    B -->|Upload / Paste| D
    B -->|Unified / Legacy Analyze| D
    C -->|View DB History| D
    D --> E --> I[Gemini API]
    E --> F
    D --> G
    D --> H --> J[(SQLite DB)]
```

## Project Structure

```text
GENAI-2/
├── app.py                          # Flask app
├── config.py                       # Config + env loading
├── requirements.txt                # Dependencies
├── .env                            # Environment variables (not in version control)
├── clauseclear.db                  # SQLite database (generated)
├── services/
│   ├── gemini_service.py           # GenAI logic, self-critique, RAG, & legacy prompts
│   ├── benchmark_service.py        # Market standard benchmark data
│   ├── playbooks.py                # Indian Legal Standard instructions
│   ├── memory_service.py           # Legacy in-memory session (falling back to DB)
│   ├── database.py                 # SQLModel models and CRUD operations
│   └── document_service.py         # PDF, DOCX, and OCR extraction
├── templates/
│   ├── base.html                   # Global layout
│   ├── index.html                  # Landing page
│   ├── analyze.html                # Main analysis workspace
│   └── history.html                # Database visualizer
├── static/
│   ├── css/style.css               # Core styling
│   └── js/app.js                   # Frontend interactivity & API calls
└── uploads/                        # Temporary file upload directory
```

## Context Engineering Implementation

Every Gemini API call follows these principles:

| Principle | Implementation |
|---|---|
| **System Prompt** | Role: "senior legal contract analyst". Behavioral guidelines + capability boundaries in every prompt |
| **Structured I/O** | Each feature has a strict JSON schema. Model instructed: "Return ONLY the JSON object. No markdown, no preamble." |
| **Session Memory** | Last 10 turns stored via SQLModel in SQLite |
| **RAG Context** | Embeds prior high-risk clauses via `text-embedding-004` and compares new clauses via cosine similarity. |
| **Self-Critique** | Evaluates its own initial analysis in a second pass to correct overstated risks or formatting errors. |
| **Legal Playbooks** | Explicitly instructs Gemini to ground analysis in specific statutes (e.g., Indian Contract Act 1872). |
| **Progressive Disclosure** | Every response: `quick_summary` → detailed analysis → `recommendations` |

## Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Landing page |
| `/analyze` | GET | Analysis page (split layout) |
| `/history` | GET | Session history page |
| `/api/upload` | POST | Upload PDF/TXT, extract text |
| `/api/analyze` | POST | Run 1 of 4 analysis features |
| `/api/chat` | POST | Follow-up questions with memory |
| `/api/memory` | GET | Get session memory state |
| `/api/clear-memory` | POST | Clear all session memory |

## Design Theme

- **Background**: Deep navy (#060a14, #0a0f1e, #111b2e)
- **Accents**: Amber/gold (#d4a853, #f0c674, #b8923e)
- **Headings**: Playfair Display (serif) from Google Fonts
- **Body text**: Inter (sans-serif)
- **Cards**: Glassmorphism with backdrop blur
- **Animations**: Float orbs, fade-in, slide-up, spin loader

## Validation

- ✅ Flask server starts successfully on `http://127.0.0.1:5000`
- ✅ All 8 routes defined and functional
- ✅ Kluster code review executed
