"""Agent 2 — Journal Reader. Author instructions → Journal Knowledge Graph (profile)."""
from __future__ import annotations

from .. import llm
from ..extract import clip

_SCHEMA = {
    "type": "object",
    "properties": {
        "journal_name": {"type": "string"},
        "scope": {"type": "string"},
        "required_sections": {"type": "array", "items": {"type": "string"}},
        "word_limits": {"type": "object", "properties": {
            "abstract": {"type": ["integer", "null"]},
            "manuscript": {"type": ["integer", "null"]},
            "introduction": {"type": ["integer", "null"]}}},
        "abstract_rules": {"type": "string"},
        "keywords_rule": {"type": "string"},
        "reference_style": {"type": "string",
                            "description": "One of APA/IEEE/Nature/Vancouver/ACM/Chicago/Harvard or as stated"},
        "max_references": {"type": ["integer", "null"]},
        "figure_rules": {"type": "string"},
        "figure_resolution_dpi": {"type": ["integer", "null"]},
        "table_rules": {"type": "string"},
        "formatting": {"type": "object", "properties": {
            "font": {"type": "string"}, "font_size": {"type": "string"},
            "line_spacing": {"type": "string"}, "margins": {"type": "string"},
            "columns": {"type": "string"}, "page_limit": {"type": ["integer", "null"]}}},
        "ethics_requirements": {"type": "array", "items": {"type": "string"}},
        "required_statements": {"type": "array", "items": {"type": "string"},
                                "description": "e.g. Funding, Conflict of Interest, Data Availability, Author Contributions"},
        "submission_rules": {"type": "array", "items": {"type": "string"}},
        "supplementary_rules": {"type": "string"},
        "citation_format_example": {"type": "string"},
    },
    "required": ["journal_name", "required_sections", "reference_style"],
}

_SYSTEM = (
    "You are the Journal Reader agent. Read the journal's author instructions / formatting guide / "
    "submission checklist and extract a precise Journal Knowledge Graph capturing EVERY concrete "
    "requirement: required sections, word limits, abstract/keyword rules, reference style + max, "
    "figure/table rules and resolution, fonts/margins/spacing/columns/page limits, ethics and "
    "required declarations (funding, conflicts, data availability, author contributions), and "
    "submission rules. If a value is not stated, leave it null/empty — never guess a hard limit.")


def read_journal(name: str, text: str) -> dict:
    body = clip(text)
    profile = llm.complete_json(
        _SYSTEM, f"JOURNAL: {name}\n\nAUTHOR INSTRUCTIONS / GUIDE TEXT:\n\n{body}",
        _SCHEMA, max_tokens=3500)
    profile.setdefault("journal_name", name)
    return profile
