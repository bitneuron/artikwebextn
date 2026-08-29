"""Neutralizes Slack mention/formatting injection in any text that could originate
from retrieved web content (result titles/summaries, run error messages) before it
reaches a Slack payload. Retrieved content is untrusted input — see prompts.py's
INJECTION_GUARD for the corresponding LLM-side guard."""
from __future__ import annotations

import re

_BARE_MENTION = re.compile(r"(?i)@(channel|here|everyone)\b")


def sanitize_for_slack(text: str | None) -> str:
    if not text:
        return ""
    # Escaping <, >, & neutralizes Slack's own bracket-mention syntax
    # (<!channel>, <@U...>, <#C...|name>) per Slack's mrkdwn escaping rules — the
    # literal "<" becomes visible text instead of a parsed token.
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Zero-width-space breaks bare word-form mentions so they don't notify anyone.
    out = _BARE_MENTION.sub("@​\\1", out)
    return out
