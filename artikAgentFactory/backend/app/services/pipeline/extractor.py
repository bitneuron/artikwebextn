"""Stage 3 — forced single-tool-use structured extraction, same pattern as
artikResearch/backend/app/llm.py::_anthropic_json. Relevance/confidence/credibility are
computed by the LLM here, as part of this one call — no separate scoring pass."""
from __future__ import annotations

import json

from app.services.model_config import get_anthropic_api_key, get_model
from app.services.pipeline.prompts import extraction_system
from app.templates.spec import TemplateSpec

_FIXED_PROPERTIES = {
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "url": {"type": "string", "description": "Must be a real URL you were given — never invented."},
    "source_name": {"type": "string"},
    "published_or_updated_at": {"type": ["string", "null"], "description": "ISO date if known, else null."},
    "relevance_score": {"type": "number"},
    "confidence_score": {"type": "number"},
    "source_credibility": {"type": "string", "enum": ["high", "medium", "low"]},
    "category": {"type": "string"},
}
_REQUIRED = ["title", "url", "summary", "relevance_score", "confidence_score", "source_credibility", "category"]


def _build_schema(template: TemplateSpec) -> dict:
    props = dict(_FIXED_PROPERTIES)
    props["sources"] = {
        "type": "array",
        "items": {"type": "object", "properties": {"url": {"type": "string"}, "title": {"type": ["string", "null"]}}},
        "description": "Any additional corroborating source URLs beyond the primary url.",
    }
    if template.result_fields:
        field_props = {rf.key: {"type": ["string", "number", "null"]} for rf in template.result_fields}
        props["fields"] = {"type": "object", "properties": field_props}
    else:
        props["fields"] = {"type": "object"}
    return {
        "type": "object",
        "properties": {
            "findings": {"type": "array", "items": {"type": "object", "properties": props, "required": _REQUIRED}},
        },
        "required": ["findings"],
    }


def extract_structured(raw_findings: list[dict], template: TemplateSpec, objective: str, max_results: int) -> list[dict]:
    import anthropic

    api_key = get_anthropic_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    client = anthropic.Anthropic(api_key=api_key)
    model = get_model("anthropic", "research")
    schema = _build_schema(template)
    tool = {"name": "emit", "description": "Return the structured research findings.", "input_schema": schema}

    user_payload = {
        "objective": objective,
        "allowed_categories": template.result_categories,
        "result_field_keys": [rf.key for rf in template.result_fields],
        "raw_research_notes": raw_findings,
    }
    user_content = json.dumps(user_payload)[:120_000]

    msg = client.messages.create(
        model=model, max_tokens=8192,
        system=extraction_system(template.system_prompt_fragment, template.result_categories),
        tools=[tool], tool_choice={"type": "tool", "name": "emit"},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in msg.content:
        if getattr(block, "type", "") == "tool_use":
            findings = (block.input or {}).get("findings", [])
            return findings[:max_results] if max_results else findings
    return []
