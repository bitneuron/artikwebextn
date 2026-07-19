# ArtikResearch Assistant

AI-powered research authoring, journal conversion, review, and publication platform — the
"GitHub Copilot for scientific research." Upload a manuscript, teach the assistant a target
journal's requirements, and it compares, rewrites, reformats, reviews, and produces a
publication-ready submission package.

Part of the **ArtikProjects** superproject (a sibling of `artikBroker`, `artikNotifier`).

---

## Status — Iteration 1 (runnable end-to-end)

The core publication lifecycle works today with real multi-provider LLM reasoning
(Claude → GPT‑5 → Gemini fallback):

**Upload paper → learn journal → gap analysis → readiness score → AI rewrite → reviewer
simulation → reference reformatting → submission package.**

### Backend (`backend/`, FastAPI + SQLite + local FS)
- **Document extraction** — PDF (PyMuPDF→pypdf), DOCX, LaTeX, Markdown, HTML, text.
- **AI agents** (`app/agents/`) — each a focused LLM tool‑call:
  1. Paper Reader → Research Knowledge Graph
  2. Journal Reader → Journal Knowledge Graph (profile)
  3. Gap Analysis → missing sections / formatting / reference / statement gaps
  4. Scientific Writer → section rewrite + the workspace chat copilot
  6. Reference → reformat + validate into APA/IEEE/Nature/Vancouver/ACM/Chicago/Harvard
  9. Compliance → per‑dimension readiness scores + acceptance prediction
  10. Reviewer Simulator → 3 distinct AI reviewers + scores
  11. Editor → submission package (Markdown/HTML/LaTeX/XML/text + cover letter + checklist)
- **Final output export** (`app/export.py`) — on upload the user picks a **Template** (target
  journal) and an **Output format** (DOCX · PDF · HTML · Markdown). `GET /api/papers/{id}/export`
  renders the current manuscript into that format: **DOCX inherits the journal's uploaded .docx
  template** (fonts/margins/page setup — e.g. the JEI Arial-11, 1‑inch, 10‑page template), **PDF**
  via reportlab, HTML/Markdown via the editor renderer.
- **APIs** — `/api/papers` (+ `/{id}/settings`, `/{id}/export`), `/api/journals`,
  `/api/analysis/{id}/{gaps,compliance,review,references,package}`, `/api/chat/{id}`,
  `/api/dashboard`, `/api/agents`, `/api/status`. Interactive docs at `/docs`.

### Frontend (`frontend/`, React + TypeScript + Vite + Tailwind)
- Dashboard (widgets + live agent catalog), My Papers (upload/list/cards/search),
  Journal Library (learn from file or pasted text + compare), **Research Workspace**
  (3‑pane: original · AI copilot · analysis tabs), Readiness ring + dimension bars,
  Reviewer panel, Reference bibliography, Submission‑package export.

### Verified
- Full pipeline tested against a sample paper + journal: journal learning, paper KG,
  gap analysis (caught missing Discussion / ethics / funding / COI / data‑availability /
  author‑contributions), 42% readiness with calibrated dimensions, 3‑reviewer sim,
  Vancouver reference reformatting (flags missing DOIs without inventing them), and the
  export package. Frontend builds clean (`tsc + vite`, 0 errors) and all screens render
  with 0 JS errors.

---

## Run

Reuses the superproject's shared Python venv (`../artikAPIs/venv`) which already has FastAPI,
PyMuPDF, python‑docx, anthropic, openai. API keys are read from `../artikAgents/agents/.env`
(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, optional `GEMINI_API_KEY`).

```bash
cd artikResearch

# Option A — production-style (backend serves the built SPA on one port)
./run.sh build      # builds frontend/dist
./run.sh api        # → http://localhost:8410

# Option B — hot-reload dev (Vite :5173 proxies /api to the backend :8410)
./run.sh            # backend + Vite dev server
```

---

## Architecture notes & swap‑ins (deferred, interfaces ready)

Iteration 1 keeps the stack lean and local so it runs immediately. These are documented
production swap‑ins behind the same functions/paths:

| Concern | Iteration 1 | Production swap‑in |
|---|---|---|
| Metadata DB | SQLite (`data/artikresearch.db`) | PostgreSQL |
| Vector / semantic index | structured JSON knowledge graphs | ChromaDB / pgvector |
| Async jobs | synchronous request handling | Celery + Redis |
| File storage | local `uploads/` + `generated/` | S3‑compatible |
| Auth | none (local) | shared Artik auth (per‑user scoping) before any deploy |
| DOCX/PDF binary export | **DONE** — python‑docx (template‑aware) + reportlab | richer LaTeX/theme fidelity |
| Figure / Table agents | structured checks + roadmap | image analysis + relabeling |
| Gemini | wired in `llm.py` | set `GEMINI_API_KEY` |

**Roadmap agents (spec'd, not in iter 1):** Literature Review, Experiment Design, Grant
Proposal, Patent, Conference; Research Notebook; and the external integrations (CrossRef,
Semantic Scholar, PubMed, arXiv, ORCID, Zotero, Overleaf, Drive, …).

## Layout
```
artikResearch/
  backend/app/{agents,routers}     FastAPI + AI pipeline
  frontend/src/{pages,components}   React + TS + Tailwind
  uploads/{papers,journals,references,figures,supplementary}
  generated/{manuscripts,pdf,latex,docx,html,xml}
  journal_library/<Journal>/profile.json   preloaded + learned journal knowledge bases
  prompts/ agents/ templates/ vector_db/ review_history/ submission_history/
  data/artikresearch.db            SQLite store
```
