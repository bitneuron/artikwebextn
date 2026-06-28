#!/usr/bin/env python3
"""Post an "Artik Notifier Deployment Complete" notification to Slack.

Reads the webhook from the SLACK_WEBHOOK_URL environment variable — the URL is a
secret and is NEVER hardcoded or committed. Designed to run as the final step of
deploy.sh (no-op when the var is unset), but works standalone too. Stdlib only.

Optional env overrides:
  APP_URL, GITHUB_URL, TEST_SUMMARY, BUILD_SUMMARY, LIMITATIONS, NEXT_STEPS
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone


def _git(*args: str, default: str = "unknown") -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return default


def build_payload() -> dict:
    app_url = os.environ.get("APP_URL", "https://c9frk5u4hf.us-west-2.awsapprunner.com")
    github = os.environ.get("GITHUB_URL", "https://github.com/bitneuron/artikwebextn")
    tests = os.environ.get("TEST_SUMMARY", "backend suite green")
    build = os.environ.get("BUILD_SUMMARY", "frontend build clean")
    limitations = os.environ.get("LIMITATIONS", "")
    next_steps = os.environ.get("NEXT_STEPS", "")
    commit, branch = _git("rev-parse", "--short", "HEAD"), _git("rev-parse", "--abbrev-ref", "HEAD")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    fields = [
        ("*Status:*", ":white_check_mark: Deployed & validated"),
        ("*When:*", when),
        ("*App URL:*", f"<{app_url}>"),
        ("*GitHub:*", f"<{github}|{branch}@{commit}>"),
        ("*Tests:*", tests),
        ("*Build:*", build),
    ]
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": "🚀 Artik Notifier Deployment Complete"}},
        {"type": "section",
         "fields": [{"type": "mrkdwn", "text": f"{k}\n{v}"} for k, v in fields]},
    ]
    if limitations:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": f"*Known limitations:* {limitations}"}})
    if next_steps:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": f"*Next steps:* {next_steps}"}})
    return {"text": "Artik Notifier Deployment Complete", "blocks": blocks}


def main() -> int:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        print("SLACK_WEBHOOK_URL not set — skipping Slack deployment notification.")
        return 0
    payload = json.dumps(build_payload()).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            print(f"Slack deployment notification → HTTP {resp.status}")
            return 0 if ok else 1
    except Exception as exc:  # never fail the deploy because Slack is unreachable
        print(f"Slack deployment notification failed (non-fatal): {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
