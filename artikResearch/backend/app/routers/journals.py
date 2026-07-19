"""Journals router — upload author instructions, learn the profile, list, compare."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .. import db, llm
from ..config import JOURNAL_LIBRARY, SUPPORTED_JOURNALS, UPLOADS
from ..extract import detect_format, extract_text
from ..agents import journal_reader

router = APIRouter(prefix="/api/journals", tags=["journals"])


def _seed_preloaded() -> None:
    """Load any journal_library/<Name>/profile.json presets into the DB once."""
    for d in JOURNAL_LIBRARY.iterdir():
        if not d.is_dir():
            continue
        prof = d / "profile.json"
        if prof.exists() and not db.get_journal_by_name(d.name):
            try:
                db.upsert_journal(d.name, json.loads(prof.read_text()), source="preloaded")
            except Exception:  # noqa: BLE001
                pass


@router.get("")
def list_journals():
    _seed_preloaded()
    js = db.list_journals()
    known = {j["name"].lower() for j in js}
    stubs = [{"name": n, "source": "supported", "profile": {}, "files": []}
             for n in SUPPORTED_JOURNALS if n.lower() not in known]
    return {"journals": js, "supported": SUPPORTED_JOURNALS, "not_yet_learned": stubs}


@router.get("/{name}")
def get_journal(name: str):
    _seed_preloaded()
    j = db.get_journal_by_name(name)
    if not j:
        return JSONResponse({"error": "journal not found — upload its author instructions to learn it"},
                            status_code=404)
    return j


@router.post("/{name}/upload")
async def upload_journal_doc(name: str, file: UploadFile = File(...), kind: str = Form("instructions")):
    """Upload an author-instructions/formatting/checklist file for a journal and learn from it."""
    dest = UPLOADS / "journals" / name
    dest.mkdir(parents=True, exist_ok=True)
    safe = Path(file.filename).name
    path = dest / safe
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    # mirror into the journal_library for the human-browsable library too
    lib = JOURNAL_LIBRARY / name
    lib.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(path, lib / safe)
    except Exception:  # noqa: BLE001
        pass
    text = extract_text(str(path), detect_format(safe))
    existing = db.get_journal_by_name(name) or {}
    files = (existing.get("files") or []) + [{"filename": safe, "kind": kind}]
    try:
        profile = journal_reader.read_journal(name, text)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"journal learning failed: {e}"}, status_code=502)
    # merge over any existing profile so multiple uploads accrete
    merged = {**(existing.get("profile") or {}), **{k: v for k, v in profile.items() if v not in (None, "", [], {})}}
    j = db.upsert_journal(name, merged, source="upload", files=files)
    return {"journal": j, "learned_from": safe}


@router.post("/{name}/learn-text")
async def learn_from_text(name: str, body: dict):
    """Learn a journal profile directly from pasted instruction text (no file)."""
    text = (body or {}).get("text", "")
    if not text.strip():
        return JSONResponse({"error": "text is required"}, status_code=400)
    try:
        profile = journal_reader.read_journal(name, text)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"journal learning failed: {e}"}, status_code=502)
    return {"journal": db.upsert_journal(name, profile, source="upload")}


_COMPARE_SCHEMA = {"type": "object", "properties": {
    "comparison": {"type": "array", "items": {"type": "object", "properties": {
        "dimension": {"type": "string"},
        "values": {"type": "object", "description": "journal_name -> value"}}}},
    "recommendation": {"type": "string"},
    "best_fit_journal": {"type": "string"}},
    "required": ["comparison", "recommendation"]}


@router.post("/compare")
async def compare_journals(body: dict):
    names = (body or {}).get("journals") or []
    profiles = {n: (db.get_journal_by_name(n) or {}).get("profile") or {} for n in names}
    have = {n: p for n, p in profiles.items() if p}
    if len(have) < 2:
        return JSONResponse({"error": "select at least two LEARNED journals to compare "
                             "(upload their instructions first)"}, status_code=400)
    paper_ctx = ""
    if body.get("paper_id"):
        p = db.get_paper(body["paper_id"])
        if p and p.get("knowledge"):
            paper_ctx = f"\nUSER PAPER FACTS:\n{json.dumps({k: p['knowledge'].get(k) for k in ('title','keywords','total_word_count','reference_count')})}"
    sys = ("You are the Journal Comparison agent. Compare the given journal profiles across word "
           "count, reference style, figure rules, submission requirements, and formatting. If a user "
           "paper is provided, estimate best fit + acceptance likelihood and recommend one.")
    user = f"JOURNAL PROFILES:\n{json.dumps(have)[:9000]}{paper_ctx}"
    try:
        out = llm.complete_json(sys, user, _COMPARE_SCHEMA, max_tokens=2500)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    return out
