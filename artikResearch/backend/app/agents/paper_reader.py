"""Agent 1 — Paper Reader. Manuscript text → Research Knowledge Graph."""
from __future__ import annotations

from .. import llm
from ..extract import clip, word_count

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "affiliations": {"type": "array", "items": {"type": "string"}},
        "abstract": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "heading": {"type": "string"},
            "word_count": {"type": "integer"},
            "summary": {"type": "string"}}, "required": ["heading"]}},
        "topic": {"type": "string"},
        "contributions": {"type": "array", "items": {"type": "string"}},
        "novelty": {"type": "string"},
        "methods": {"type": "string"},
        "results": {"type": "string"},
        "figures": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "caption": {"type": "string"}}}},
        "tables": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "caption": {"type": "string"}}}},
        "references": {"type": "array", "items": {"type": "string"},
                       "description": "Reference strings as they appear (first ~40)"},
        "reference_count": {"type": "integer"},
        "ethics_statement": {"type": "boolean"},
        "funding_statement": {"type": "boolean"},
        "conflict_of_interest": {"type": "boolean"},
        "acknowledgements": {"type": "boolean"},
        "summary": {"type": "string", "description": "2-3 sentence plain-language summary"},
    },
    "required": ["title", "abstract", "sections", "summary"],
}

_SYSTEM = (
    "You are the Paper Reader agent for a scientific-publishing assistant. Read the manuscript "
    "text and extract a precise, structured Research Knowledge Graph. Do not invent content — if a "
    "field is absent, use an empty value and set the boolean statements to false. Estimate section "
    "word counts. Capture figure/table captions and the first ~40 reference strings verbatim.")


def read_paper(text: str) -> dict:
    body = clip(text)
    kg = llm.complete_json(_SYSTEM, f"MANUSCRIPT TEXT:\n\n{body}", _SCHEMA, max_tokens=4000)
    kg.setdefault("keywords", [])
    kg["total_word_count"] = word_count(text)
    kg.setdefault("reference_count", len(kg.get("references") or []))
    return kg
