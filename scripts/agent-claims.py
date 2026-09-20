#!/usr/bin/env python3
"""Shared file-claim registry so Claude Code and OpenAI Codex can work in this
repo at the same time without silently overwriting each other's edits.

Both assistants use the same file, `.agent-claims.json` at the repo root
(gitignored, machine-local). A claim says "agent X is editing these paths".
Before editing, an assistant checks the file; if another agent holds a live
claim on the path it must stop and tell the user instead of editing.

    agent-claims.py claim   --agent claude --task "price changes" PATH [PATH ...]
    agent-claims.py release --agent claude [PATH ...]        # no PATH = all
    agent-claims.py check   --agent claude PATH              # exit 2 if blocked
    agent-claims.py list
    agent-claims.py hook    --agent claude                   # Claude PreToolUse

Paths are repo-relative. A claim on a directory covers everything under it.
Claims older than STALE_HOURS are ignored (a crashed session never locks the
repo forever) and are pruned on the next write.

Claude enforces this with a PreToolUse hook (`hook` subcommand). Codex has no
equivalent hook, so its side is instruction-only via AGENTS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / ".agent-claims.json"
STALE_HOURS = 8
AGENTS = ("claude", "codex")


# ── storage ──────────────────────────────────────────────────────────────────
def _load() -> list[dict]:
    try:
        data = json.loads(CLAIMS.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [c for c in data.get("claims", []) if _fresh(c)]


def _save(claims: list[dict]) -> None:
    tmp = CLAIMS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"claims": claims}, indent=2) + "\n")
    os.replace(tmp, CLAIMS)


def _fresh(c: dict) -> bool:
    return (time.time() - c.get("ts", 0)) < STALE_HOURS * 3600


def _rel(p: str) -> str:
    """Repo-relative POSIX path; absolute paths outside the repo pass through."""
    path = Path(p)
    if not path.is_absolute():
        path = (Path.cwd() / path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _covers(claimed: str, target: str) -> bool:
    return target == claimed or target.startswith(claimed.rstrip("/") + "/")


def _holder(claims: list[dict], target: str, me: str) -> dict | None:
    for c in claims:
        if c["agent"] == me:
            continue
        if any(_covers(p, target) for p in c["paths"]):
            return c
    return None


def _age(c: dict) -> str:
    mins = int((time.time() - c["ts"]) / 60)
    return f"{mins}m" if mins < 120 else f"{mins // 60}h"


# ── commands ─────────────────────────────────────────────────────────────────
def cmd_claim(a) -> int:
    claims = _load()
    paths = [_rel(p) for p in a.paths]
    for p in paths:
        h = _holder(claims, p, a.agent)
        if h:
            print(f"BLOCKED: {p} is claimed by {h['agent']} ({_age(h)} ago): {h['task']}",
                  file=sys.stderr)
            return 2
    # merge into an existing claim from the same agent + task if present
    for c in claims:
        if c["agent"] == a.agent and c["task"] == a.task:
            c["paths"] = sorted(set(c["paths"]) | set(paths))
            c["ts"] = time.time()
            break
    else:
        claims.append({"agent": a.agent, "task": a.task, "paths": paths,
                       "ts": time.time(),
                       "started": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _save(claims)
    print(f"claimed for {a.agent}: {', '.join(paths)}")
    return 0


def cmd_release(a) -> int:
    claims = _load()
    if not a.paths:
        kept = [c for c in claims if c["agent"] != a.agent]
        n = len(claims) - len(kept)
    else:
        rel = {_rel(p) for p in a.paths}
        kept, n = [], 0
        for c in claims:
            if c["agent"] == a.agent:
                before = len(c["paths"])
                c["paths"] = [p for p in c["paths"] if p not in rel]
                n += before - len(c["paths"])
                if not c["paths"]:
                    continue
            kept.append(c)
    _save(kept)
    print(f"released {n} claim path(s) for {a.agent}")
    return 0


def cmd_check(a) -> int:
    h = _holder(_load(), _rel(a.path), a.agent)
    if h:
        print(f"BLOCKED: {_rel(a.path)} is claimed by {h['agent']} ({_age(h)} ago): {h['task']}")
        return 2
    print("ok")
    return 0


def cmd_list(a) -> int:
    claims = _load()
    if not claims:
        print("no active claims")
        return 0
    for c in claims:
        print(f"[{c['agent']}] {c['task']}  ({_age(c)} ago)")
        for p in c["paths"]:
            print(f"    {p}")
    return 0


def cmd_hook(a) -> int:
    """Claude Code PreToolUse hook: stdin is the tool-call JSON."""
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    fp = (payload.get("tool_input") or {}).get("file_path")
    if not fp:
        return 0
    target = _rel(fp)
    h = _holder(_load(), target, a.agent)
    if not h:
        return 0
    reason = (f"{target} is claimed by {h['agent']} ({_age(h)} ago) for: {h['task']}. "
              f"Do not edit it. Tell the user, or run "
              f"`python3 scripts/agent-claims.py release --agent {h['agent']}` "
              f"if that session is finished.")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": f"⛔ {reason}",
    }))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def agent_arg(p):
        p.add_argument("--agent", required=True, choices=AGENTS)

    p = sub.add_parser("claim"); agent_arg(p)
    p.add_argument("--task", required=True)
    p.add_argument("paths", nargs="+")
    p.set_defaults(fn=cmd_claim)

    p = sub.add_parser("release"); agent_arg(p)
    p.add_argument("paths", nargs="*")
    p.set_defaults(fn=cmd_release)

    p = sub.add_parser("check"); agent_arg(p)
    p.add_argument("path")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)

    p = sub.add_parser("hook"); agent_arg(p)
    p.set_defaults(fn=cmd_hook)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
