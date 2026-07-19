"""Analysis router — gap analysis, compliance/readiness, reviewer sim, references, export."""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db
from ..extract import extract_text
from ..agents import compliance, editor, gap_analysis, reference, reviewer

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _paper_kg(pid: str):
    p = db.get_paper(pid)
    if not p:
        return None, None, JSONResponse({"error": "paper not found"}, status_code=404)
    if not p.get("knowledge"):
        return p, None, JSONResponse({"error": "run /api/papers/{id}/read first"}, status_code=409)
    return p, p["knowledge"], None


def _journal_profile(name: str) -> dict:
    j = db.get_journal_by_name(name) if name else None
    return (j or {}).get("profile") or {}


@router.post("/{pid}/gaps")
def run_gaps(pid: str, body: dict = None):
    p, kg, err = _paper_kg(pid)
    if err:
        return err
    journal = (body or {}).get("journal") or p.get("target_journal") or ""
    profile = _journal_profile(journal)
    try:
        gaps = gap_analysis.analyze_gaps(kg, profile)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    db.add_analysis(pid, journal, "gaps", gaps)
    return {"journal": journal, "gaps": gaps}


@router.post("/{pid}/compliance")
def run_compliance(pid: str, body: dict = None):
    p, kg, err = _paper_kg(pid)
    if err:
        return err
    journal = (body or {}).get("journal") or p.get("target_journal") or ""
    profile = _journal_profile(journal)
    gaps = (db.latest_analysis(pid, "gaps") or {}).get("result")
    if not gaps:
        try:
            gaps = gap_analysis.analyze_gaps(kg, profile)
            db.add_analysis(pid, journal, "gaps", gaps)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)}, status_code=502)
    try:
        report = compliance.score(kg, profile, gaps)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    db.add_analysis(pid, journal, "compliance", report)
    db.update_paper(pid, readiness=report.get("overall"))
    return {"journal": journal, "readiness": report}


@router.post("/{pid}/review")
def run_review(pid: str, body: dict = None):
    p, kg, err = _paper_kg(pid)
    if err:
        return err
    journal = (body or {}).get("journal") or p.get("target_journal") or ""
    text = extract_text(p["path"], p["fmt"])
    try:
        rev = reviewer.simulate(kg, text, journal)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    db.add_analysis(pid, journal, "review", rev)
    return {"review": rev}


@router.post("/{pid}/references")
def run_references(pid: str, body: dict = None):
    p, kg, err = _paper_kg(pid)
    if err:
        return err
    style = (body or {}).get("style") or _journal_profile(
        (body or {}).get("journal") or p.get("target_journal") or "").get("reference_style") or "IEEE"
    refs = kg.get("references") or []
    if not refs:
        return JSONResponse({"error": "no references extracted from this paper"}, status_code=422)
    try:
        out = reference.reformat(refs, style)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    db.add_analysis(pid, "", "references", out)
    return out


@router.post("/{pid}/package")
def build_package(pid: str, body: dict = None):
    p, kg, err = _paper_kg(pid)
    if err:
        return err
    journal = (body or {}).get("journal") or p.get("target_journal") or ""
    profile = _journal_profile(journal)
    gaps = (db.latest_analysis(pid, "gaps") or {}).get("result") or {}
    # use the latest generated manuscript version if present, else the extracted text
    versions = db.list_versions(pid)
    manuscript = db.get_version(versions[0]["id"])["content"] if versions else extract_text(p["path"], p["fmt"])
    try:
        pkg = editor.build_package(kg, manuscript, journal, profile, gaps)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    db.add_analysis(pid, journal, "package", {"checklist": pkg["submission_checklist"],
                                              "note": pkg["note"]})
    return pkg


@router.get("/{pid}/history")
def analysis_history(pid: str):
    return {"gaps": db.list_analyses(pid, "gaps"),
            "compliance": db.list_analyses(pid, "compliance"),
            "review": db.list_analyses(pid, "review"),
            "versions": db.list_versions(pid)}
