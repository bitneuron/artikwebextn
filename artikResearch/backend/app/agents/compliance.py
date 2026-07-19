"""Agent 9 — Compliance / Publication-Readiness scoring.

Combines the paper KG + journal profile + gap analysis into per-dimension scores (0-100) and an
overall readiness percentage. Deterministic penalties are applied on top of the LLM's dimension
scores so the number can't drift wildly from the concrete gap count.
"""
from __future__ import annotations

import json

from .. import llm

DIMENSIONS = ["formatting", "references", "grammar", "figures", "tables", "compliance",
              "novelty", "scientific_writing", "journal_match"]

_SCHEMA = {
    "type": "object",
    "properties": {
        **{d: {"type": "integer", "minimum": 0, "maximum": 100} for d in DIMENSIONS},
        "acceptance_prediction": {"type": "integer", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
        "top_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": DIMENSIONS + ["acceptance_prediction"],
}

_SYSTEM = (
    "You are the Compliance agent. Given a paper's knowledge graph, the target journal profile, and "
    "a gap analysis, score publication readiness on each dimension 0-100 (formatting, references, "
    "grammar, figures, tables, compliance, novelty, scientific_writing, journal_match) and predict "
    "acceptance probability 0-100. Be calibrated: many high-severity gaps must lower the relevant "
    "scores. Give 3-5 concrete top_actions.")


def score(paper_kg: dict, journal_profile: dict, gaps: dict) -> dict:
    user = (f"PAPER:\n{json.dumps(paper_kg)[:6000]}\n\nJOURNAL:\n{json.dumps(journal_profile)[:4000]}\n\n"
            f"GAPS:\n{json.dumps(gaps)[:4000]}")
    out = llm.complete_json(_SYSTEM, user, _SCHEMA, max_tokens=1500)
    # Deterministic guardrail: penalize by observed gaps so the score reflects reality.
    hi = sum(1 for v in (gaps.get("formatting_violations") or []) if v.get("severity") == "high")
    out["formatting"] = max(0, min(100, int(out.get("formatting", 80)) - 8 * hi))
    if gaps.get("missing_sections"):
        out["compliance"] = max(0, int(out.get("compliance", 80)) - 6 * len(gaps["missing_sections"]))
    if gaps.get("missing_statements"):
        out["compliance"] = max(0, int(out["compliance"]) - 5 * len(gaps["missing_statements"]))
    if gaps.get("reference_issues"):
        out["references"] = max(0, int(out.get("references", 85)) - 5 * len(gaps["reference_issues"]))
    scores = [int(out.get(d, 0)) for d in DIMENSIONS]
    out["overall"] = round(sum(scores) / len(scores))
    out["dimensions"] = {d: int(out.get(d, 0)) for d in DIMENSIONS}
    return out
