"""Agent 4 — Scientific Writer + the conversational command handler.

`rewrite_section` reworks one section to a journal's style. `chat` handles free-form workspace
commands ("rewrite the abstract", "reduce word count to 250", "convert references to IEEE",
"suggest a better title") by routing to the right action and returning updated manuscript text
plus a short assistant reply.
"""
from __future__ import annotations

import json

from .. import llm

_WRITER_SYSTEM = (
    "You are the Scientific Writer agent. Rewrite scientific prose to improve grammar, readability, "
    "flow, and academic tone WITHOUT changing the scientific meaning, claims, numbers, or citations. "
    "Match the target journal's writing style and word limits when given. Never invent results.")


def rewrite_section(section_name: str, section_text: str, journal_profile: dict | None = None,
                    instruction: str = "") -> str:
    jp = f"\nTARGET JOURNAL STYLE:\n{json.dumps(journal_profile)[:2500]}" if journal_profile else ""
    extra = f"\nEXTRA INSTRUCTION: {instruction}" if instruction else ""
    user = (f"Rewrite the '{section_name}' section below.{jp}{extra}\n\n"
            f"--- SECTION ---\n{section_text[:8000]}")
    return llm.complete_text(_WRITER_SYSTEM, user, max_tokens=3000)


_CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["rewrite", "shorten", "reformat_references",
                                              "suggest_title", "improve", "generate_section",
                                              "answer", "cover_letter", "reviewer_response"]},
        "target": {"type": "string", "description": "Section/element the action applies to, if any"},
        "reply": {"type": "string", "description": "Short assistant reply to show in chat"},
        "updated_manuscript": {"type": "string",
                               "description": "The FULL updated manuscript (markdown) if the action changed it; else empty"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action", "reply"],
}

_CHAT_SYSTEM = (
    "You are ArtikResearch Assistant's writing copilot inside a manuscript workspace. The user gives "
    "natural-language commands about THEIR manuscript. Decide the action and, when the command edits "
    "the manuscript, return the FULL updated manuscript in markdown in `updated_manuscript` "
    "(preserving all sections, only changing what was asked). Preserve scientific meaning, numbers, "
    "and citations. Keep `reply` short. If the command only asks a question, action='answer' and "
    "leave updated_manuscript empty. Respect any journal profile and word limits provided.")


def chat(command: str, manuscript: str, paper_kg: dict | None = None,
         journal_profile: dict | None = None, history: list | None = None) -> dict:
    ctx = ""
    if journal_profile:
        ctx += f"\nTARGET JOURNAL PROFILE:\n{json.dumps(journal_profile)[:2500]}"
    if paper_kg:
        ctx += f"\nPAPER FACTS:\n{json.dumps({k: paper_kg.get(k) for k in ('title','keywords','reference_count')})[:800]}"
    hist = ""
    if history:
        hist = "\nRECENT CHAT:\n" + "\n".join(f"{h['role']}: {h['content'][:300]}" for h in history[-6:])
    user = (f"USER COMMAND: {command}{ctx}{hist}\n\n"
            f"--- CURRENT MANUSCRIPT (markdown) ---\n{manuscript[:14000]}")
    out = llm.complete_json(_CHAT_SYSTEM, user, _CHAT_SCHEMA, max_tokens=4000)
    return out
