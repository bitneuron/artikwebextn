"""Agent 5 — Formatting / Template Conversion.

`convert_to_template` restructures the whole manuscript to a target journal's template:
- reorders + renames sections to the journal's required_sections (e.g. JEI: Summary,
  Introduction, Results, Discussion, Materials & Methods, …),
- enforces the abstract/summary word limit,
- converts references to the journal's citation style,
- inserts clearly-marked placeholders for any REQUIRED section/statement that is missing
  (so nothing is silently invented),
while preserving all scientific content, numbers, and citations. Returns full markdown.
"""
from __future__ import annotations

import json

from .. import llm

_SYSTEM = (
    "You are the Formatting & Template-Conversion agent. Convert the user's manuscript to the "
    "TARGET JOURNAL's template. Follow these rules strictly:\n"
    "1. Reorder and rename the manuscript's sections to match the journal's required_sections, in "
    "that exact order. Map the paper's existing content into the right target sections (e.g. an "
    "'Abstract' becomes 'Summary' if the journal requires 'Summary').\n"
    "2. Enforce the abstract/summary word limit if given.\n"
    "3. Convert in-text citations and the reference list to the journal's reference_style.\n"
    "4. For any REQUIRED section or required statement (ethics, funding, conflict of interest, data "
    "availability, author contributions, acknowledgements) that the paper LACKS, insert the heading "
    "with a clearly-marked placeholder like '[To be completed: …]'. NEVER fabricate results, data, "
    "citations, or approvals.\n"
    "5. Preserve every scientific claim, number, figure/table reference, and citation from the "
    "original. Improve grammar/flow/academic tone only.\n"
    "Return the COMPLETE converted manuscript in Markdown, using '#'/'##' headings.")

_SCHEMA = {
    "type": "object",
    "properties": {
        "manuscript_markdown": {"type": "string", "description": "The full converted manuscript in markdown"},
        "changes": {"type": "array", "items": {"type": "string"},
                    "description": "Short list of the structural/format changes applied"},
        "placeholders_added": {"type": "array", "items": {"type": "string"},
                               "description": "Required sections/statements inserted as placeholders"},
    },
    "required": ["manuscript_markdown"],
}


def convert_to_template(manuscript: str, paper_kg: dict, journal_profile: dict) -> dict:
    user = (f"TARGET JOURNAL TEMPLATE PROFILE:\n{json.dumps(journal_profile)[:5000]}\n\n"
            f"PAPER FACTS (for reference-style + title):\n"
            f"{json.dumps({k: paper_kg.get(k) for k in ('title', 'keywords', 'references')})[:3000]}\n\n"
            f"--- CURRENT MANUSCRIPT (markdown) ---\n{manuscript[:15000]}")
    out = llm.complete_json(_SYSTEM, user, _SCHEMA, max_tokens=8000)
    out.setdefault("changes", [])
    out.setdefault("placeholders_added", [])
    return out
