"""Agent 11 — Editor. Assemble the submission package: manuscript exports + cover letter +
submission checklist + reviewer-response template.

Iteration 1 emits Markdown, HTML, LaTeX, and plain-text/XML-ish forms deterministically from the
manuscript markdown (no external LaTeX/Word toolchain required), plus an LLM-written cover letter
and reviewer-response template. DOCX/PDF binary rendering is a documented fast-follow.
"""
from __future__ import annotations

import html as _html
import json
import re

from .. import llm


def _inline(s: str) -> str:
    esc = _html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)


def md_to_html(md: str, title: str = "") -> str:
    out, para = [], []

    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    for ln in md.splitlines():
        h = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if h:
            flush()
            lvl = len(h.group(1))
            out.append(f"<h{lvl}>{_html.escape(h.group(2))}</h{lvl}>")
        elif ln.strip() == "":
            flush()
        else:
            para.append(_inline(ln))
    flush()
    body = "\n".join(out)
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{_html.escape(title)}</title>"
            "<style>body{font-family:Georgia,serif;max-width:820px;margin:40px auto;line-height:1.6;"
            "padding:0 20px}h1,h2,h3{font-family:Helvetica,Arial,sans-serif}</style></head><body>"
            f"{body}</body></html>")


def md_to_latex(md: str, title: str = "") -> str:
    out = [r"\documentclass[11pt]{article}", r"\usepackage[margin=1in]{geometry}",
           r"\usepackage{graphicx}", r"\usepackage{cite}",
           (r"\title{" + _tex(title) + "}") if title else "", r"\begin{document}",
           r"\maketitle" if title else ""]
    for ln in md.splitlines():
        h = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if h:
            cmd = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}[len(h.group(1))]
            out.append(f"\\{cmd}{{{_tex(h.group(2))}}}")
        elif ln.strip():
            out.append(_tex(ln))
        else:
            out.append("")
    out.append(r"\end{document}")
    return "\n".join(o for o in out if o is not None)


def _tex(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    for a, b in [("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")]:
        s = s.replace(a, b)
    return s


def md_to_xml(md: str, kg: dict) -> str:
    def esc(x):
        return _html.escape(str(x or ""))
    secs = ""
    for m in re.finditer(r"^#{1,3}\s+(.*)$", md, flags=re.M):
        secs += f"    <sec><title>{esc(m.group(1))}</title></sec>\n"
    return ("<?xml version='1.0' encoding='UTF-8'?>\n<article>\n  <front>\n"
            f"    <article-title>{esc(kg.get('title'))}</article-title>\n"
            f"    <abstract>{esc(kg.get('abstract'))}</abstract>\n  </front>\n  <body>\n{secs}"
            "  </body>\n</article>")


_COVER_SYSTEM = ("You are the Editor agent. Write a concise, professional cover letter to the "
                 "editor-in-chief for this manuscript submission, and a reviewer-response letter "
                 "template with numbered placeholders. Return JSON.")
_COVER_SCHEMA = {"type": "object", "properties": {
    "cover_letter": {"type": "string"}, "reviewer_response_template": {"type": "string"}},
    "required": ["cover_letter", "reviewer_response_template"]}


def cover_and_response(kg: dict, journal: str) -> dict:
    user = (f"JOURNAL: {journal}\nTITLE: {kg.get('title')}\nABSTRACT: {kg.get('abstract','')[:1500]}\n"
            f"CONTRIBUTIONS: {json.dumps(kg.get('contributions') or [])[:800]}")
    try:
        return llm.complete_json(_COVER_SYSTEM, user, _COVER_SCHEMA, max_tokens=1500)
    except Exception:  # noqa: BLE001
        return {"cover_letter": f"Dear Editor,\n\nPlease consider our manuscript '{kg.get('title')}' "
                f"for publication in {journal}.\n\nSincerely,\nThe Authors",
                "reviewer_response_template": "Reviewer #1\nComment 1: …\nResponse: …\n"}


def submission_checklist(journal_profile: dict, gaps: dict) -> list[dict]:
    items = []
    for s in (journal_profile.get("required_sections") or []):
        items.append({"item": f"Section present: {s}",
                      "done": s not in (gaps.get("missing_sections") or [])})
    for st in (journal_profile.get("required_statements") or []):
        items.append({"item": f"Statement included: {st}",
                      "done": st not in " ".join(gaps.get("missing_statements") or [])})
    items.append({"item": f"References in {journal_profile.get('reference_style','required')} style",
                  "done": not (gaps.get("reference_issues"))})
    items.append({"item": "Within word limits", "done": not (gaps.get("word_count_violations"))})
    items.append({"item": "Figures meet resolution/caption rules", "done": not (gaps.get("figure_issues"))})
    return items


def build_package(kg: dict, manuscript_md: str, journal: str, journal_profile: dict,
                  gaps: dict) -> dict:
    title = kg.get("title") or "Manuscript"
    cr = cover_and_response(kg, journal)
    return {
        "formats": {
            "markdown": manuscript_md,
            "html": md_to_html(manuscript_md, title),
            "latex": md_to_latex(manuscript_md, title),
            "xml": md_to_xml(manuscript_md, kg),
            "text": re.sub(r"[#*]", "", manuscript_md),
        },
        "cover_letter": cr["cover_letter"],
        "reviewer_response_template": cr["reviewer_response_template"],
        "submission_checklist": submission_checklist(journal_profile or {}, gaps or {}),
        "note": "DOCX/PDF binary rendering is a documented fast-follow; text/markdown/html/latex/xml are produced now.",
    }
