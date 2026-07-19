"""Unified LLM client — Claude / GPT-5 / Gemini with provider fallback + JSON tool-calls.

Every agent calls `complete_json(system, user, schema)` to get a validated dict back, or
`complete_text(...)` for prose. Providers are tried in order (default: anthropic → openai →
gemini); each provider walks its model chain. No provider configured → a clear, safe error.
Never raises secrets; keys come from the environment only.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .config import Models


class LLMError(RuntimeError):
    pass


def available_providers() -> list[str]:
    out = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        out.append("anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        out.append("openai")
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        out.append("gemini")
    return out


def _order(preferred: str | None) -> list[str]:
    avail = available_providers()
    if preferred and preferred in avail:
        return [preferred] + [p for p in avail if p != preferred]
    return avail


# ── Anthropic ────────────────────────────────────────────────────────────────
def _anthropic_json(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = {"name": "emit", "description": "Return the structured result.", "input_schema": schema}
    last = None
    for model in Models.chain("anthropic"):
        try:
            msg = client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                tools=[tool], tool_choice={"type": "tool", "name": "emit"},
                messages=[{"role": "user", "content": user}])
            for b in msg.content:
                if getattr(b, "type", "") == "tool_use":
                    return b.input
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"anthropic failed: {last}")


def _anthropic_text(system: str, user: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    last = None
    for model in Models.chain("anthropic"):
        try:
            msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                         messages=[{"role": "user", "content": user}])
            return "".join(getattr(b, "text", "") for b in msg.content)
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"anthropic failed: {last}")


# ── OpenAI ───────────────────────────────────────────────────────────────────
def _openai_json(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    tool = {"type": "function", "function": {"name": "emit", "description": "Return the result.",
                                             "parameters": schema}}
    last = None
    for model in Models.chain("openai"):
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{"role": "system", "content": system},
                                       {"role": "user", "content": user}],
                tools=[tool], tool_choice={"type": "function", "function": {"name": "emit"}},
                max_completion_tokens=max_tokens, reasoning_effort="minimal")
            calls = resp.choices[0].message.tool_calls
            if calls:
                return json.loads(calls[0].function.arguments)
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"openai failed: {last}")


def _openai_text(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    last = None
    for model in Models.chain("openai"):
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{"role": "system", "content": system},
                                       {"role": "user", "content": user}],
                max_completion_tokens=max_tokens, reasoning_effort="minimal")
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"openai failed: {last}")


# ── Gemini (optional) ────────────────────────────────────────────────────────
def _gemini_text(system: str, user: str, max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"])
    last = None
    for model in Models.chain("gemini"):
        try:
            m = genai.GenerativeModel(model, system_instruction=system)
            return m.generate_content(user).text
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"gemini failed: {last}")


# ── public API ───────────────────────────────────────────────────────────────
def complete_json(system: str, user: str, schema: dict, *, provider: str | None = None,
                  max_tokens: int = 3000) -> dict[str, Any]:
    order = _order(provider)
    if not order:
        raise LLMError("no LLM provider configured (set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)")
    last = None
    for p in order:
        try:
            if p == "anthropic":
                return _anthropic_json(system, user, schema, max_tokens)
            if p == "openai":
                return _openai_json(system, user, schema, max_tokens)
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"all providers failed for JSON: {last}")


def complete_text(system: str, user: str, *, provider: str | None = None,
                  max_tokens: int = 3000) -> str:
    order = _order(provider)
    if not order:
        raise LLMError("no LLM provider configured (set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)")
    last = None
    for p in order:
        try:
            if p == "anthropic":
                return _anthropic_text(system, user, max_tokens)
            if p == "openai":
                return _openai_text(system, user, max_tokens)
            if p == "gemini":
                return _gemini_text(system, user, max_tokens)
        except Exception as e:  # noqa: BLE001
            last = e
    raise LLMError(f"all providers failed for text: {last}")
