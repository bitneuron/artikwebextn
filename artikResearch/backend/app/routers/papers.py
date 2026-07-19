"""Papers router — upload, list, get, delete, and the extraction/read pipeline."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import db, export
from ..config import GENERATED, UPLOADS
from ..extract import detect_format, extract_text, word_count
from ..agents import formatter, paper_reader

router = APIRouter(prefix="/api/papers", tags=["papers"])
_ALLOWED = {"pdf", "docx", "latex", "markdown", "text", "html"}


@router.get("")
def list_papers():
    return {"papers": db.list_papers()}


@router.post("")
async def upload_paper(file: UploadFile = File(...), name: str = Form(None),
                       target_journal: str = Form(None), output_format: str = Form("docx")):
    fmt = detect_format(file.filename or "")
    if fmt not in _ALLOWED:
        return JSONResponse({"error": f"unsupported format '{fmt}' "
                             f"(allowed: {sorted(_ALLOWED)})"}, status_code=400)
    out_fmt = (output_format or "docx").lower()
    if out_fmt not in export.FORMATS:
        return JSONResponse({"error": f"output_format must be one of {export.FORMATS}"}, status_code=400)
    dest = UPLOADS / "papers"
    safe = Path(file.filename).name
    path = dest / safe
    i = 1
    while path.exists():
        path = dest / f"{Path(safe).stem}_{i}{Path(safe).suffix}"
        i += 1
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    paper = db.add_paper(name or Path(safe).stem, safe, str(path), fmt)
    upd = {"output_format": out_fmt, "status": "extracted"}
    if target_journal:
        upd["target_journal"] = target_journal
    db.update_paper(paper["id"], **upd)
    text = extract_text(str(path), fmt)   # extract now; structured read happens in /read
    return {**db.get_paper(paper["id"]), "chars": len(text), "words": word_count(text)}


@router.put("/{pid}/settings")
def update_settings(pid: str, body: dict):
    """Update the target journal (template) and/or output format after upload."""
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    upd = {}
    if "target_journal" in (body or {}):
        upd["target_journal"] = body["target_journal"] or None
    if "output_format" in (body or {}):
        of = (body["output_format"] or "docx").lower()
        if of not in export.FORMATS:
            return JSONResponse({"error": f"output_format must be one of {export.FORMATS}"}, status_code=400)
        upd["output_format"] = of
    return db.update_paper(pid, **upd) if upd else p


@router.post("/{pid}/convert")
def convert_and_export(pid: str, body: dict = None):
    """Convert the current manuscript INTO the selected template (target journal) — restructuring
    sections + reference style + inserting placeholders for missing required items — then render it
    to the selected output format and write the file into generated/<fmt>/. Returns a download URL.

    Triggered when the user selects a Template + Output format. Saves the converted markdown as a
    new version and the source under generated/manuscripts/.
    """
    body = body or {}
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    journal = (body.get("journal") or p.get("target_journal") or "").strip()
    if not journal:
        return JSONResponse({"error": "select a template (target journal) first"}, status_code=400)
    fmt = (body.get("output_format") or p.get("output_format") or "docx").lower()
    if fmt not in export.FORMATS:
        return JSONResponse({"error": f"output_format must be one of {export.FORMATS}"}, status_code=400)
    if not p.get("knowledge"):
        return JSONResponse({"error": "run Read paper first so the converter has the paper's structure"},
                            status_code=409)
    jrow = db.get_journal_by_name(journal)
    profile = (jrow or {}).get("profile") or {}
    if not profile:
        return JSONResponse({"error": f"journal '{journal}' not learned yet — upload its template/"
                             "instructions in the Journal Library"}, status_code=409)

    # persist the selection
    db.update_paper(pid, target_journal=journal, output_format=fmt)

    # source manuscript = latest generated version, else the extracted original
    versions = db.list_versions(pid)
    source = (db.get_version(versions[0]["id"])["content"] if versions
              else extract_text(p["path"], p["fmt"]))
    if not source.strip():
        return JSONResponse({"error": "no manuscript content to convert"}, status_code=422)

    try:
        conv = formatter.convert_to_template(source, p["knowledge"], profile)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"conversion failed: {e}"}, status_code=502)
    manuscript = conv.get("manuscript_markdown") or ""
    if not manuscript.strip():
        return JSONResponse({"error": "converter returned an empty manuscript"}, status_code=502)

    version = db.add_version(pid, f"convert → {journal} ({fmt})", manuscript)
    db.update_paper(pid, status="converted")
    # write the markdown source into generated/manuscripts/ for traceability
    title = p["knowledge"].get("title") or p.get("name") or "manuscript"
    src_path = GENERATED / "manuscripts" / f"{export._safe(title)}.md"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(manuscript)

    try:
        out_path, _ = export.render(manuscript, title=title, journal=journal, profile=profile, fmt=fmt)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"export failed: {e}"}, status_code=502)

    rel = str(out_path.relative_to(GENERATED.parent))
    return {"ok": True, "journal": journal, "format": fmt,
            "output_file": rel, "download_url": f"/api/papers/{pid}/export?format={fmt}",
            "version": version, "changes": conv.get("changes"),
            "placeholders_added": conv.get("placeholders_added"),
            "manuscript_markdown": manuscript}


@router.get("/{pid}/export")
def export_paper(pid: str, format: str = None):
    """Render the CURRENT manuscript (latest generated version, else the original) into the
    chosen format and return the file. Defaults to the paper's selected output_format."""
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    fmt = (format or p.get("output_format") or "docx").lower()
    if fmt not in export.FORMATS:
        return JSONResponse({"error": f"format must be one of {export.FORMATS}"}, status_code=400)
    versions = db.list_versions(pid)
    manuscript = (db.get_version(versions[0]["id"])["content"] if versions
                  else extract_text(p["path"], p["fmt"]))
    if not manuscript.strip():
        return JSONResponse({"error": "no manuscript content to export"}, status_code=422)
    title = (p.get("knowledge") or {}).get("title") or p.get("name") or "manuscript"
    journal = p.get("target_journal") or ""
    from .. import db as _db
    jrow = _db.get_journal_by_name(journal) if journal else None
    profile = (jrow or {}).get("profile") or {}
    try:
        path, media = export.render(manuscript, title=title, journal=journal, profile=profile, fmt=fmt)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"export failed: {e}"}, status_code=502)
    return FileResponse(str(path), media_type=media, filename=path.name)


@router.get("/{pid}")
def get_paper(pid: str):
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    return p


@router.get("/{pid}/text")
def get_paper_text(pid: str):
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    return {"text": extract_text(p["path"], p["fmt"])}


@router.post("/{pid}/read")
def read_paper(pid: str):
    """Run the Paper Reader agent → Research Knowledge Graph (cached on the paper)."""
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    text = extract_text(p["path"], p["fmt"])
    if not text.strip() or text.startswith("("):
        return JSONResponse({"error": f"could not extract text: {text[:200]}"}, status_code=422)
    try:
        kg = paper_reader.read_paper(text)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"paper read failed: {e}"}, status_code=502)
    db.update_paper(pid, knowledge=kg, summary=kg.get("summary", ""), status="analyzed")
    return {"knowledge": kg}


@router.delete("/{pid}")
def delete_paper(pid: str):
    if not db.get_paper(pid):
        return JSONResponse({"error": "paper not found"}, status_code=404)
    db.delete_paper(pid)
    return {"ok": True}
