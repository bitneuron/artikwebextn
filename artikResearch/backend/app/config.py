"""ArtikResearch Assistant — configuration and paths.

Secrets come ONLY from the environment (or the shared artikAgents/.env in dev) — never
hardcoded. Storage is local-filesystem + SQLite for iteration 1; Postgres / pgvector /
ChromaDB / S3 are documented swap-ins (see README) behind these same paths/interfaces.
"""
from __future__ import annotations

import os
from pathlib import Path

# artikResearch/ (two levels up from backend/app/config.py)
ROOT = Path(__file__).resolve().parents[2]

UPLOADS = ROOT / "uploads"
GENERATED = ROOT / "generated"
JOURNAL_LIBRARY = ROOT / "journal_library"
VECTOR_DB = ROOT / "vector_db"
REVIEW_HISTORY = ROOT / "review_history"
SUBMISSION_HISTORY = ROOT / "submission_history"
DATA = ROOT / "data"
DB_PATH = Path(os.environ.get("ARTIKRESEARCH_DB", str(DATA / "artikresearch.db")))

for _d in (UPLOADS, UPLOADS / "papers", UPLOADS / "journals", UPLOADS / "references",
           UPLOADS / "figures", UPLOADS / "supplementary", GENERATED, JOURNAL_LIBRARY,
           VECTOR_DB, REVIEW_HISTORY, SUBMISSION_HISTORY, DATA):
    _d.mkdir(parents=True, exist_ok=True)

# Reference styles the Reference Agent supports.
REFERENCE_STYLES = ["APA", "IEEE", "Nature", "Vancouver", "ACM", "Chicago", "Harvard"]

# Preloaded + user-uploaded journals.
SUPPORTED_JOURNALS = ["Nature", "Science", "Cell", "IEEE", "ACM", "Springer", "Elsevier",
                      "PLOS", "MDPI", "Frontiers", "arXiv", "EmergingInvestigators", "Custom"]

# Sections a well-formed empirical manuscript is expected to contain.
STANDARD_SECTIONS = ["Title", "Abstract", "Keywords", "Introduction", "Related Work",
                     "Methods", "Results", "Discussion", "Conclusion", "References"]


def _load_env_file() -> None:
    """Dev convenience: pull ANTHROPIC/OPENAI/GEMINI keys from artikAgents/agents/.env."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return
    candidate = ROOT.parent / "artikAgents" / "agents" / ".env"
    if candidate.exists():
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()


class Models:
    # Newest-first chains; env overrides win. Mirrors the artik model-config pattern.
    ANTHROPIC = [os.environ.get("ANTHROPIC_MODEL"), "claude-opus-5"]
    OPENAI = [os.environ.get("OPENAI_MODEL"), "gpt-6-astra"]
    GEMINI = [os.environ.get("GEMINI_MODEL"), "gemini-2.0-flash"]

    @staticmethod
    def chain(provider: str) -> list[str]:
        c = {"anthropic": Models.ANTHROPIC, "openai": Models.OPENAI, "gemini": Models.GEMINI}
        return [m for m in c.get(provider, []) if m]


# Shared provider compatibility (also copied into the standalone Broker image).
import importlib.util as _import_util
_compat_path = next(p for p in [ROOT.parent / "artikAgents/agents/shared/llm_compat.py"] if p.exists())
_compat_spec = _import_util.spec_from_file_location("artik_llm_compat", _compat_path)
_compat = _import_util.module_from_spec(_compat_spec)
_compat_spec.loader.exec_module(_compat)
openai_create = _compat.openai_create
anthropic_create = _compat.anthropic_create
