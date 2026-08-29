"""Stage 2 — one Claude call per query using the native server-side web_search tool.
Tolerant of individual query failures (a network hiccup on query 2 shouldn't kill a
4-query run); raises only if every single query failed."""
from __future__ import annotations

from app.services.model_config import get_anthropic_api_key, get_model
from app.services.pipeline.prompts import SEARCH_SYSTEM

WEB_SEARCH_TOOL_TYPE = "web_search_20250305"


def _extract_text_and_citations(content_blocks) -> tuple[str, list[dict]]:
    text_parts: list[str] = []
    citations: list[dict] = []
    sources_touched = 0
    for block in content_blocks:
        btype = getattr(block, "type", "")
        if btype == "text":
            text = getattr(block, "text", "") or ""
            text_parts.append(text)
            for c in (getattr(block, "citations", None) or []):
                url = getattr(c, "url", None)
                if url:
                    citations.append({"url": url, "title": getattr(c, "title", None)})
        elif btype == "web_search_tool_result":
            result_content = getattr(block, "content", None)
            if isinstance(result_content, list):
                sources_touched += len(result_content)
                for item in result_content:
                    url = getattr(item, "url", None)
                    if url:
                        citations.append({"url": url, "title": getattr(item, "title", None)})
    return "\n".join(text_parts), citations, sources_touched  # type: ignore[return-value]


def web_search_pass(queries: list[str], max_uses: int) -> tuple[list[dict], int, bool]:
    import anthropic

    api_key = get_anthropic_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured (checked env and artikAgents/agents/.env)")
    client = anthropic.Anthropic(api_key=api_key)
    model = get_model("anthropic", "research")

    raw_findings: list[dict] = []
    total_sources = 0
    had_errors = False

    for query in queries:
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SEARCH_SYSTEM,
                tools=[{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_uses}],
                messages=[{"role": "user", "content": f"Research query: {query}"}],
            )
            text, citations, sources_touched = _extract_text_and_citations(msg.content)
            total_sources += sources_touched
            raw_findings.append({"query": query, "text": text, "citations": citations})
        except Exception:  # noqa: BLE001 — one bad query shouldn't kill the whole run
            had_errors = True
            continue

    if not raw_findings:
        raise RuntimeError("all web search queries failed")
    return raw_findings, total_sources, had_errors
