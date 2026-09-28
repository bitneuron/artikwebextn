"""Read-only bridge to the Stock Analysis Agent's output, plus its durable copy.

The agent writes latest_recommendations.json into its per-instance data folder. That
folder is on the container's ephemeral disk on App Runner, so after every run the
runner also saves the latest result and the run history into the app_kv table of the
users DB (which Litestream replicates). Reads prefer the file and fall back to the DB,
so the card and Results survive a redeploy.

This module never scores anything and never changes a verdict — it only moves the
agent's JSON around and formats it (Results, Slack digest, the brief's prompt).
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request
from pathlib import Path

import agents_store as store

_KV_PREFIX = "stock_recs:"
_HISTORY_KEEP = 30


def data_dir(agent_id: str) -> Path:
    return store.ANALYSIS_DATA_DIR / agent_id


# ---------------------------------------------------------------------------
# Durable copy (app_kv)
# ---------------------------------------------------------------------------

def _kv_get(agent_id: str) -> dict:
    try:
        with store._db_conn() as c:
            row = c.execute("SELECT value FROM app_kv WHERE key=?", (_KV_PREFIX + agent_id,)).fetchone()
        return json.loads(row[0]) if row else {}
    except Exception:  # noqa: BLE001
        return {}


def _kv_set(agent_id: str, value: dict) -> None:
    try:
        with store._db_conn() as c:
            c.execute("INSERT INTO app_kv (key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (_KV_PREFIX + agent_id, json.dumps(value, default=str)))
    except Exception:  # noqa: BLE001
        pass


def _kv_delete(agent_id: str) -> None:
    try:
        with store._db_conn() as c:
            c.execute("DELETE FROM app_kv WHERE key=?", (_KV_PREFIX + agent_id,))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def latest(agent_id: str) -> dict | None:
    p = data_dir(agent_id) / "latest_recommendations.json"
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return _kv_get(agent_id).get("latest")


def agent_run(agent_id: str, run_id: str | None) -> dict | None:
    """The agent's own run_history row for run_id (or its newest row)."""
    p = data_dir(agent_id) / "run_history.jsonl"
    if not p.exists():
        return None
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if run_id:
        for r in reversed(rows):
            if r.get("run_id") == run_id:
                return r
    return rows[-1] if rows else None


def history(agent_id: str, limit: int = 20) -> list[dict]:
    return list(reversed(_kv_get(agent_id).get("history") or []))[:limit]


def latest_broker_run(agent_id: str) -> dict | None:
    h = history(agent_id, 1)
    return h[0] if h else None


# ---------------------------------------------------------------------------
# Writes (runner only)
# ---------------------------------------------------------------------------

def record_run(agent_id: str, broker_run: dict) -> None:
    """Append a Broker run record and snapshot the latest result into the DB."""
    kv = _kv_get(agent_id)
    hist = (kv.get("history") or []) + [broker_run]
    kv["history"] = hist[-_HISTORY_KEEP:]
    lat = latest(agent_id)
    if lat and lat.get("run_id") == broker_run.get("run_id"):
        kv["latest"] = lat
    _kv_set(agent_id, kv)


def purge(agent_id: str) -> dict:
    d = data_dir(agent_id)
    existed = d.exists()
    if existed:
        shutil.rmtree(d, ignore_errors=True)
    had_kv = bool(_kv_get(agent_id))
    _kv_delete(agent_id)
    return {"data_dir_deleted": existed, "history_deleted": had_kv}


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def picks(run: dict | None) -> dict:
    run = run or {}
    return {k: run.get(k) for k in ("buy", "hold", "sell", "no_score", "disagreements", "candidates_found")}


def results(agent_id: str) -> dict:
    lat = latest(agent_id) or {}
    rows = lat.get("rows") or []
    groups = {v: [r for r in rows if r.get("verdict") == v] for v in ("BUY", "HOLD", "SELL", "NO_SCORE")}
    changes = [r for r in rows if (r.get("change") or "").find("→") > 0]
    return {
        "agent_id": agent_id,
        "available": bool(rows),
        "run": {k: v for k, v in lat.items() if k != "rows"} if lat else None,
        "groups": groups,
        "changes": [{"ticker": r["ticker"], "change": r["change"], "score": r.get("score")} for r in changes],
        "new_names": [r["ticker"] for r in rows if r.get("change") == "new" and r.get("origin") == "discovered"],
        "history": history(agent_id, 20),
        "note": lat.get("note") or "Verdicts come from the Artik engine score. Not financial advice.",
    }


def brief_prompt(res: dict) -> str | None:
    """Facts for the written brief. The model summarises; it is told it cannot change a verdict."""
    g = res.get("groups") or {}
    if not any(g.get(v) for v in ("BUY", "HOLD", "SELL")):
        return None
    lines = []
    for v in ("BUY", "HOLD", "SELL"):
        for r in g.get(v, [])[:12]:
            st = (r.get("street") or {}).get("street_verdict") or "no coverage"
            why = "; ".join((r.get("strengths") or [])[:1] + (r.get("risks") or [])[:1])
            lines.append(f"- {r['ticker']} {v} score {r.get('score')} ({r.get('archetype')}), "
                         f"street {st}, {r.get('origin')}, change {r.get('change')}. {why}")
    return ("Today's Artik engine verdicts:\n" + "\n".join(lines)
            + "\n\nWrite the daily brief in 3-5 sentences: the strongest BUYs, notable SELLs, "
              "any verdict changes, and where the engine disagrees with the street.")


BRIEF_SYSTEM = (
    "You write Artik Broker's daily stock brief. The BUY/HOLD/SELL verdicts come from the "
    "Artik scoring engine and are final: report them exactly, never change, soften or add a "
    "verdict, and never invent a price target or figure that is not in the input. Plain English, "
    "no bullet points, no preamble. End with: 'Engine output, not financial advice.'"
)


# ---------------------------------------------------------------------------
# Slack digest (optional; STOCK_RECS_SLACK_WEBHOOK)
# ---------------------------------------------------------------------------

def build_digest(agent_name: str, res: dict) -> str | None:
    g = res.get("groups") or {}
    if not any(g.get(v) for v in ("BUY", "HOLD", "SELL")):
        return None

    def fmt(r):
        st = (r.get("street") or {}).get("street_verdict")
        flag = " ⚠️ street says " + st if r.get("agreement") == "disagrees" and st else ""
        ch = f" _({r['change']})_" if "→" in (r.get("change") or "") else (" 🆕" if r.get("change") == "new" else "")
        return f"• *{r['ticker']}* {r.get('score')}{ch}{flag}"

    out = [f"*{agent_name} — daily recommendations*"]
    for v, icon in (("BUY", "🟢"), ("HOLD", "⚪"), ("SELL", "🔴")):
        rows = g.get(v) or []
        if rows:
            out.append(f"\n{icon} *{v}* ({len(rows)})\n" + "\n".join(fmt(r) for r in rows[:12]))
    if g.get("NO_SCORE"):
        out.append("\nNo engine score: " + ", ".join(r["ticker"] for r in g["NO_SCORE"]))
    out.append("\n_Verdicts are the Artik engine's score bands. Not financial advice._")
    return "\n".join(out)


def post_digest(agent_name: str, res: dict) -> tuple[bool, str]:
    hook = os.environ.get("STOCK_RECS_SLACK_WEBHOOK", "").strip()
    if not hook:
        return False, "STOCK_RECS_SLACK_WEBHOOK not set"
    text = build_digest(agent_name, res)
    if not text:
        return False, "nothing to post"
    req = urllib.request.Request(hook, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — configured webhook
            return 200 <= r.status < 300, f"http {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:160]
