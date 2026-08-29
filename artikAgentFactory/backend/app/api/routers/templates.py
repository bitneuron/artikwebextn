from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_active_user
from app.templates.registry import get_template, list_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _out(t) -> dict:
    d = asdict(t)
    d.pop("system_prompt_fragment", None)  # internal prompt detail, not for the frontend
    return d


@router.get("", dependencies=[Depends(get_current_active_user)])
def list_all():
    return [_out(t) for t in list_templates()]


@router.get("/{template_id}", dependencies=[Depends(get_current_active_user)])
def get_one(template_id: str):
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, "unknown template")
    return _out(t)
