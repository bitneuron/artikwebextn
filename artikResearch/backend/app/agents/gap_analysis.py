"""Agent 3 — Gap Analysis. Paper KG vs Journal KG → gaps, violations, missing items."""
from __future__ import annotations

import json

from .. import llm

_SCHEMA = {
    "type": "object",
    "properties": {
        "missing_sections": {"type": "array", "items": {"type": "string"}},
        "formatting_violations": {"type": "array", "items": {"type": "object", "properties": {
            "rule": {"type": "string"}, "issue": {"type": "string"},
            "severity": {"type": "string", "enum": ["high", "medium", "low"]}}}},
        "reference_issues": {"type": "array", "items": {"type": "string"}},
        "word_count_violations": {"type": "array", "items": {"type": "string"}},
        "missing_statements": {"type": "array", "items": {"type": "string"},
                               "description": "e.g. ethics, funding, conflict of interest, acknowledgements, data availability"},
        "figure_issues": {"type": "array", "items": {"type": "string"}},
        "table_issues": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"},
                            "description": "Prioritized, actionable fixes"},
        "gap_count": {"type": "integer"},
    },
    "required": ["missing_sections", "formatting_violations", "recommendations"],
}

_SYSTEM = (
    "You are the Gap Analysis agent. Compare a paper's structured knowledge graph against a target "
    "journal's requirements and list every concrete gap: missing/required sections, formatting "
    "violations (with severity), reference-style issues, word-count violations, missing ethics/"
    "declaration statements, and figure/table problems. Be specific and cite the journal rule. "
    "Then give a short prioritized list of recommendations. Do not fabricate journal rules that "
    "aren't in the provided profile.")


def analyze_gaps(paper_kg: dict, journal_profile: dict) -> dict:
    user = (f"PAPER KNOWLEDGE GRAPH:\n{json.dumps(paper_kg, indent=1)[:9000]}\n\n"
            f"JOURNAL PROFILE:\n{json.dumps(journal_profile, indent=1)[:6000]}")
    out = llm.complete_json(_SYSTEM, user, _SCHEMA, max_tokens=3000)
    out["gap_count"] = (len(out.get("missing_sections") or []) + len(out.get("formatting_violations") or [])
                        + len(out.get("reference_issues") or []) + len(out.get("word_count_violations") or [])
                        + len(out.get("missing_statements") or []) + len(out.get("figure_issues") or [])
                        + len(out.get("table_issues") or []))
    return out
