"""Chat router — the AI Copilot inside the research workspace."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db
from ..extract import extract_text
from ..agents import scientific_writer

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/{pid}")
def history(pid: str):
    return {"messages": db.list_chats(pid)}


@router.post("/{pid}")
def send(pid: str, body: dict):
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    command = (body or {}).get("message", "").strip()
    if not command:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # current manuscript = latest generated version, else the extracted original
    versions = db.list_versions(pid)
    manuscript = (db.get_version(versions[0]["id"])["content"] if versions
                  else extract_text(p["path"], p["fmt"]))
    journal = p.get("target_journal") or (body or {}).get("journal") or ""
    jprofile = (db.get_journal_by_name(journal) or {}).get("profile") if journal else None

    db.add_chat(pid, "user", command)
    try:
        out = scientific_writer.chat(command, manuscript, p.get("knowledge"), jprofile,
                                     db.list_chats(pid))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)
    reply = out.get("reply", "")
    db.add_chat(pid, "assistant", reply)

    updated = out.get("updated_manuscript") or ""
    version = None
    if updated.strip() and updated.strip() != manuscript.strip():
        version = db.add_version(pid, f"{out.get('action','edit')}: {command[:60]}", updated)
    return {"reply": reply, "action": out.get("action"), "suggestions": out.get("suggestions") or [],
            "updated_manuscript": updated or None, "version": version}


@router.get("/{pid}/manuscript")
def current_manuscript(pid: str):
    p = db.get_paper(pid)
    if not p:
        return JSONResponse({"error": "paper not found"}, status_code=404)
    versions = db.list_versions(pid)
    if versions:
        return {"content": db.get_version(versions[0]["id"])["content"],
                "version_id": versions[0]["id"], "source": "generated"}
    return {"content": extract_text(p["path"], p["fmt"]), "version_id": None, "source": "original"}
