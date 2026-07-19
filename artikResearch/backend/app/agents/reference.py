"""Agent 6 — Reference Agent. Reformat + validate references into a target citation style."""
from __future__ import annotations

import json

from .. import llm
from ..config import REFERENCE_STYLES

_SCHEMA = {
    "type": "object",
    "properties": {
        "style": {"type": "string"},
        "formatted": {"type": "array", "items": {"type": "string"},
                      "description": "Each reference reformatted into the target style"},
        "issues": {"type": "array", "items": {"type": "string"},
                   "description": "Missing DOIs, incomplete entries, duplicates, inconsistent style"},
        "duplicates_removed": {"type": "integer"},
        "bibliography_markdown": {"type": "string"},
    },
    "required": ["style", "formatted"],
}

_SYSTEM = (
    "You are the Reference agent. Reformat the provided references into the requested citation style "
    "exactly (APA / IEEE / Nature / Vancouver / ACM / Chicago / Harvard). Flag missing DOIs, "
    "incomplete entries, and duplicates (remove duplicates). Never invent bibliographic data you "
    "don't have — flag it as an issue instead. Return a clean numbered/formatted bibliography.")


def reformat(references: list[str], style: str) -> dict:
    style = style if style in REFERENCE_STYLES else "IEEE"
    user = f"TARGET STYLE: {style}\n\nREFERENCES:\n{json.dumps(references)[:9000]}"
    out = llm.complete_json(_SYSTEM, user, _SCHEMA, max_tokens=3500)
    out["style"] = style
    return out
