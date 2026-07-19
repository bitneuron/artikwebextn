"""Agent 10 — Reviewer Simulator. Three independent AI reviewers → comments + scores."""
from __future__ import annotations

import json

from .. import llm

_SCHEMA = {
    "type": "object",
    "properties": {
        "reviewers": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "recommendation": {"type": "string",
                               "enum": ["Accept", "Minor Revision", "Major Revision", "Reject"]},
            "major_comments": {"type": "array", "items": {"type": "string"}},
            "minor_comments": {"type": "array", "items": {"type": "string"}},
            "questions": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": ["name", "recommendation", "major_comments"]}},
        "editor_summary": {"type": "string"},
        "novelty_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "publication_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "acceptance_probability": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["reviewers", "acceptance_probability"],
}

_SYSTEM = (
    "You are a peer-review panel simulator for a target journal. Produce THREE distinct, realistic "
    "reviewers (Reviewer #1, #2, #3) with different emphases (rigor, novelty, clarity). Each gives a "
    "recommendation, major + minor comments, questions, weaknesses, and a 1-5 confidence. Then an "
    "editor summary, novelty score, publication score, and overall acceptance probability. Be "
    "constructive and specific to THIS manuscript — no boilerplate.")


def simulate(paper_kg: dict, manuscript_excerpt: str, journal: str = "") -> dict:
    user = (f"TARGET JOURNAL: {journal or 'a competitive peer-reviewed venue'}\n\n"
            f"PAPER KNOWLEDGE GRAPH:\n{json.dumps(paper_kg)[:6000]}\n\n"
            f"MANUSCRIPT EXCERPT:\n{manuscript_excerpt[:6000]}")
    return llm.complete_json(_SYSTEM, user, _SCHEMA, max_tokens=3500)
