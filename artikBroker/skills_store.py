"""Skills Management store for artikBroker.

The Artik methodology lives as markdown "skills" under the stock-analysis knowledge
base. This module lets analysts view/edit/version those files. The deterministic
scoring engine (artik_engine) does NOT parse these files at runtime, so editing a
skill never changes scoring behaviour — only the live .md content on disk changes
when a published version is written.

Live skill files: <SKILLS_DIR>/<category>/<Name>.md
Version history + drafts: config/skill_versions.json (stdlib JSON; no new deps).
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_DIR = Path(os.environ.get(
    "SKILLS_DIR",
    str(HERE.parent / "artikAgents" / "agents" / "knowledge_bases"
        / "stock_analysis" / "skills"))).resolve()
STORE_PATH = HERE / "config" / "skill_versions.json"

_lock = threading.RLock()

# Folder → display label (unknown folders title-case automatically).
CATEGORY_LABELS = {
    "agents": "Agents", "core": "Core", "business_quality": "Business Quality",
    "portfolio": "Portfolio", "quant": "Quant", "research": "Research",
    "orchestrator": "Orchestrator", "mandate": "Mandate", "risk": "Risk",
    "technical": "Technical",
}
# Categories whose docs define the scoring methodology the engine implements.
_ENGINE_CATEGORIES = {"core", "business_quality", "quant", "mandate", "orchestrator"}

# Skill file → the scoring component it documents (+ the inputs it covers).
IMPACT_MAP = {
    "Financial_Strength_Skill.md": {"component": "financial_strength_score",
        "impacts": ["Debt / equity", "Interest coverage", "Liquidity", "Altman Z"]},
    "Growth_Analysis_Skill.md": {"component": "growth_score",
        "impacts": ["Revenue growth", "EPS growth", "FCF growth", "Hypergrowth archetype"]},
    "Quality_Analysis_Skill.md": {"component": "quality_score",
        "impacts": ["ROIC", "Margins", "FCF conversion", "Compounder archetype"]},
    "Technical_Analysis_Skill.md": {"component": "technical_score",
        "impacts": ["RSI", "MACD", "Trend", "Bollinger bands"]},
    "Value_Analysis_Skill.md": {"component": "value_score",
        "impacts": ["P/E", "P/FCF", "EV/EBITDA", "Earnings yield"]},
    "Archetype_Multiplier_Skill.md": {"component": "archetype_multiplier",
        "impacts": ["Archetype classification", "Quality multiplier (0.80–1.20)"]},
    "Peer_Normalization_Skill.md": {"component": "peer_percentiles",
        "impacts": ["S&P 500 sector-cohort percentiles"]},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── id ↔ path (traversal-safe) ────────────────────────────────────────────────
def path_to_id(rel: str) -> str:
    return rel[:-3].replace("/", "__") if rel.endswith(".md") else rel.replace("/", "__")


def id_to_relpath(skill_id: str) -> str:
    return skill_id.replace("__", "/") + ".md"


def _abs_for_id(skill_id: str) -> Path | None:
    """Resolve a skill_id to an absolute path, refusing anything outside SKILLS_DIR."""
    if not skill_id or "/" in skill_id or "\\" in skill_id or ".." in skill_id:
        return None
    p = (SKILLS_DIR / id_to_relpath(skill_id)).resolve()
    try:
        p.relative_to(SKILLS_DIR)
    except ValueError:
        return None
    return p


def _pretty(filename: str) -> str:
    return re.sub(r"\.md$", "", filename).replace("_", " ").strip()


def _category_label(folder: str) -> str:
    return CATEGORY_LABELS.get(folder, folder.replace("_", " ").title())


# ── version store ─────────────────────────────────────────────────────────────
def _read_store() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_store(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


# ── listing ───────────────────────────────────────────────────────────────────
def _meta_for(abs_path: Path) -> dict:
    rel = abs_path.relative_to(SKILLS_DIR).as_posix()
    parts = rel.split("/")
    folder = parts[0] if len(parts) > 1 else "uncategorized"
    fname = abs_path.name
    sid = path_to_id(rel)
    store = _read_store().get(sid, {})
    impact = IMPACT_MAP.get(fname)
    try:
        mtime = datetime.fromtimestamp(abs_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        mtime = None
    return {
        "skill_id": sid,
        "name": _pretty(fname),
        "filename": fname,
        "category": folder,
        "category_label": _category_label(folder),
        "path": "skills/" + rel,
        "last_updated": mtime,
        "version": store.get("current_version", 1),
        "status": "draft" if store.get("draft") else "published",
        "has_draft": bool(store.get("draft")),
        "draft_requested": bool((store.get("draft") or {}).get("requested")),
        "used_by_engine": bool(impact) or (folder in _ENGINE_CATEGORIES),
        "impact_component": (impact or {}).get("component"),
        "impacts": (impact or {}).get("impacts", []),
    }


def list_skills() -> list[dict]:
    if not SKILLS_DIR.exists():
        return []
    out = []
    for p in sorted(SKILLS_DIR.rglob("*.md")):
        if p.name == "SKILLS_LIBRARY.md":
            continue   # the index doc, not a scoring skill
        out.append(_meta_for(p))
    return out


def get_skill(skill_id: str) -> dict | None:
    abs_path = _abs_for_id(skill_id)
    if not abs_path or not abs_path.exists():
        return None
    meta = _meta_for(abs_path)
    store = _read_store().get(skill_id, {})
    meta["content"] = abs_path.read_text(encoding="utf-8", errors="replace")
    meta["draft"] = store.get("draft")          # {content,author,updated_at,change_summary,requested} | None
    meta["version_count"] = len(store.get("versions", []))
    return meta


def versions(skill_id: str) -> list[dict]:
    store = _read_store().get(skill_id, {})
    vs = [{k: v for k, v in ver.items() if k != "content"} | {"has_content": True}
          for ver in store.get("versions", [])]
    vs.sort(key=lambda v: v.get("version", 0), reverse=True)
    return vs


def version_content(skill_id: str, version: int) -> str | None:
    for ver in _read_store().get(skill_id, {}).get("versions", []):
        if ver.get("version") == version:
            return ver.get("content")
    return None


# ── mutations ─────────────────────────────────────────────────────────────────
class SkillError(ValueError):
    """Validation problem (bad name/category, traversal, duplicate, …)."""


def save_draft(skill_id: str, content: str, author: str, change_summary: str = "",
               requested: bool = False) -> dict:
    abs_path = _abs_for_id(skill_id)
    if not abs_path or not abs_path.exists():
        raise SkillError("skill not found")
    with _lock:
        data = _read_store()
        s = data.setdefault(skill_id, {})
        s["draft"] = {"content": content, "author": author, "updated_at": _now(),
                      "change_summary": change_summary, "requested": bool(requested)}
        _write_store(data)
    return get_skill(skill_id)


def discard_draft(skill_id: str) -> dict:
    with _lock:
        data = _read_store()
        if skill_id in data and data[skill_id].get("draft"):
            data[skill_id]["draft"] = None
            _write_store(data)
    return get_skill(skill_id)


def publish(skill_id: str, author: str, change_summary: str, content: str | None = None) -> dict:
    """Write the (draft or provided) content to the LIVE skill file and record a
    published version. Requires a change summary (governance)."""
    if not (change_summary or "").strip():
        raise SkillError("a change summary is required to publish")
    abs_path = _abs_for_id(skill_id)
    if not abs_path or not abs_path.exists():
        raise SkillError("skill not found")
    with _lock:
        data = _read_store()
        s = data.setdefault(skill_id, {"versions": [], "current_version": 1})
        body = content if content is not None else (s.get("draft") or {}).get("content")
        if body is None:
            raise SkillError("nothing to publish — no draft or content provided")
        # archive previous published versions
        for ver in s.get("versions", []):
            if ver.get("status") == "published":
                ver["status"] = "archived"
        new_ver = int(s.get("current_version", 0)) + 1 if s.get("versions") else 1
        s.setdefault("versions", []).append({
            "version": new_ver, "author": author, "created_at": _now(),
            "change_summary": change_summary, "content": body, "status": "published"})
        s["current_version"] = new_ver
        s["draft"] = None
        abs_path.write_text(body, encoding="utf-8")   # ← only published content hits the live path
        _write_store(data)
    return get_skill(skill_id)


def _safe_filename(name: str) -> str:
    base = re.sub(r"\.md$", "", (name or "").strip(), flags=re.I)
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    return (base or "New_Skill") + ".md"


def create_skill(*, name: str, category: str, content: str, author: str,
                 description: str = "") -> dict:
    category = re.sub(r"[^a-z0-9_]+", "", (category or "").strip().lower().replace(" ", "_"))
    if not category:
        raise SkillError("category is required")
    fname = _safe_filename(name)
    rel = f"{category}/{fname}"
    abs_path = (SKILLS_DIR / rel).resolve()
    try:
        abs_path.relative_to(SKILLS_DIR)
    except ValueError:
        raise SkillError("invalid skill path")
    if abs_path.exists():
        raise SkillError("a skill with that name already exists in this category")
    body = content if (content or "").strip() else (
        f"# {_pretty(fname)}\n\n" + (f"> {description}\n\n" if description else "")
        + "## Overview\n\n_Describe this skill…_\n")
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(body, encoding="utf-8")
    sid = path_to_id(rel)
    with _lock:
        data = _read_store()
        data[sid] = {"current_version": 1, "draft": None, "versions": [{
            "version": 1, "author": author, "created_at": _now(),
            "change_summary": "Initial version" + (f" — {description}" if description else ""),
            "content": body, "status": "published"}]}
        _write_store(data)
    return get_skill(sid)


def duplicate_skill(skill_id: str, author: str) -> dict:
    src = get_skill(skill_id)
    if not src:
        raise SkillError("skill not found")
    base = re.sub(r"\.md$", "", src["filename"]) + "_Copy"
    return create_skill(name=base, category=src["category"], content=src["content"],
                        author=author, description="")


def delete_skill(skill_id: str) -> None:
    abs_path = _abs_for_id(skill_id)
    if not abs_path or not abs_path.exists():
        raise SkillError("skill not found")
    abs_path.unlink()
    with _lock:
        data = _read_store()
        if skill_id in data:
            del data[skill_id]
            _write_store(data)
