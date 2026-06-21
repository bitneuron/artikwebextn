"""Natural-language → ticker resolution for managed agents.

The Stock News Collector can be configured with a plain-English statement
("AI infrastructure leaders", "companies hurt by a strong dollar") instead of a
hand-typed ticker list. This module turns that statement into a list of US-listed
operating-company tickers using the SAME Claude-first / GPT-fallback cascade that
powers Broker's AI Search — it just returns tickers (no scoring, no filters).

Self-contained on purpose (own key lookup) so agent_runner can import it without a
circular dependency on app.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

_SYSTEM = (
    "You are a stock-discovery resolver. Convert the user's plain-English statement "
    "into a list of US-listed operating-company tickers most relevant to it, for news "
    "tracking. Use correct, real ticker symbols. Prefer liquid, well-known names with "
    "strong exposure to the theme. Do NOT invent tickers and do NOT include ETFs or "
    "funds. Return 4-12 of the most relevant names. Always call return_tickers."
)

_TOOL = {
    "name": "return_tickers",
    "description": "Return the tickers most relevant to the statement, plus a one-line summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "One sentence describing the interpreted intent."},
            "tickers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "reason": {"type": "string", "description": "Short reason this name fits the statement."},
                    },
                    "required": ["ticker"],
                },
            },
        },
        "required": ["tickers"],
    },
}


def _key(name: str) -> str | None:
    """API key from env (AWS) or the local artikAgents/.env (dev)."""
    k = os.environ.get(name)
    if k:
        return k
    envf = HERE.parent / "artikAgents" / "agents" / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _clean(plan: dict | None, limit: int = 12) -> list[str]:
    out, seen = [], set()
    for c in (plan or {}).get("tickers", []):
        t = (c.get("ticker") or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


def _resolve_anthropic(query: str, key: str) -> dict | None:
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1200,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "return_tickers"},
        messages=[{"role": "user", "content": query}],
    )
    return next((b.input for b in msg.content if b.type == "tool_use"), None)


def _resolve_openai(query: str, key: str) -> dict | None:
    from openai import OpenAI
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": query}],
        tools=[{"type": "function", "function": {
            "name": _TOOL["name"], "description": _TOOL["description"],
            "parameters": _TOOL["input_schema"],
        }}],
        tool_choice={"type": "function", "function": {"name": _TOOL["name"]}},
        max_completion_tokens=1200,
        reasoning_effort="minimal",
    )
    calls = resp.choices[0].message.tool_calls
    return json.loads(calls[0].function.arguments) if calls else None


def resolve(query: str, limit: int = 12) -> dict:
    """Resolve a plain-English statement to tickers.

    Returns {ok, tickers, summary, provider} or {ok:False, error}.
    """
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "empty query"}

    akey, okey = _key("ANTHROPIC_API_KEY"), _key("OPENAI_API_KEY")
    if not akey and not okey:
        return {"ok": False, "error": "no ANTHROPIC_API_KEY or OPENAI_API_KEY configured"}

    plan, provider, last_err = None, None, None
    if akey:
        try:
            plan, provider = _resolve_anthropic(query, akey), "claude"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]
    if plan is None and okey:
        try:
            plan, provider = _resolve_openai(query, okey), "gpt"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]

    tickers = _clean(plan, limit)
    if not tickers:
        return {"ok": False, "error": last_err or "could not interpret the statement into tickers"}
    return {"ok": True, "tickers": tickers,
            "summary": (plan or {}).get("summary", ""), "provider": provider}
