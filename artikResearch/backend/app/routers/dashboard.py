"""Dashboard router — aggregate widgets + agent catalog + system status."""
from __future__ import annotations

from fastapi import APIRouter

from .. import db, llm
from ..config import REFERENCE_STYLES, SUPPORTED_JOURNALS

router = APIRouter(prefix="/api", tags=["dashboard"])

AGENTS = [
    {"id": 1, "name": "Paper Reader", "status": "active", "desc": "Manuscript → Research Knowledge Graph"},
    {"id": 2, "name": "Journal Reader", "status": "active", "desc": "Author instructions → Journal Knowledge Graph"},
    {"id": 3, "name": "Gap Analysis", "status": "active", "desc": "Paper vs journal → gaps & violations"},
    {"id": 4, "name": "Scientific Writer", "status": "active", "desc": "Rewrite sections; workspace copilot"},
    {"id": 5, "name": "Formatting", "status": "partial", "desc": "Fonts/margins/headings (export in Editor)"},
    {"id": 6, "name": "Reference", "status": "active", "desc": "Reformat + validate into 7 citation styles"},
    {"id": 7, "name": "Figure", "status": "planned", "desc": "Resolution/caption/label checks"},
    {"id": 8, "name": "Table", "status": "planned", "desc": "Formatting/alignment/units checks"},
    {"id": 9, "name": "Compliance", "status": "active", "desc": "Per-dimension readiness scoring"},
    {"id": 10, "name": "Reviewer Simulator", "status": "active", "desc": "3 AI reviewers + acceptance probability"},
    {"id": 11, "name": "Editor", "status": "active", "desc": "Submission package: md/html/latex/xml + cover letter"},
]


@router.get("/dashboard")
def dashboard():
    papers = db.list_papers()
    journals = db.list_journals()
    in_progress = [p for p in papers if p.get("status") in ("uploaded", "extracted", "analyzed")]
    recent = papers[:5]
    ready = [p for p in papers if (p.get("readiness") or 0) >= 85]
    avg_ready = round(sum(p.get("readiness") or 0 for p in papers) / len(papers)) if papers else 0
    return {
        "papers_in_progress": len(in_progress),
        "recent_papers": recent,
        "recent_journals": [j["name"] for j in journals[:5]],
        "publication_readiness_avg": avg_ready,
        "papers_ready": len(ready),
        "total_papers": len(papers),
        "journals_learned": len(journals),
        "recommendations": [
            "Upload your target journal's author instructions to unlock gap analysis.",
            "Run the Reviewer Simulator before submitting to catch major concerns early.",
        ],
    }


@router.get("/agents")
def agents():
    return {"agents": AGENTS}


@router.get("/status")
def status():
    return {"providers": llm.available_providers(), "reference_styles": REFERENCE_STYLES,
            "supported_journals": SUPPORTED_JOURNALS, "ok": True}
