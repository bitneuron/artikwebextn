#!/usr/bin/env python3
"""Trading Desk execution bridge — runs on the Mac next to the IBKR Client Portal Gateway.

Polls the (AWS or local) artikBroker for APPROVED live orders, executes them through the LOCAL
IBKR gateway (the only machine that can reach it), and reports results back. Orders wait safely
in the queue when this bridge is offline or the gateway session has expired — nothing is lost.

Usage:
    export ARTIK_BASE="https://hpzkeypha3.us-west-2.awsapprunner.com"   # or http://localhost:8100
    export TRADING_BRIDGE_KEY="<same value set on the server>"
    export IBKR_BASE_URL="https://localhost:5001/v1/api"
    export IBKR_VERIFY_SSL="false"
    python trading_bridge.py            # poll loop (15s)
    python trading_bridge.py --once     # single pass (good for testing)

Safety: executes only orders the server marked `approved` (human-approved or admin AUTO mode);
refuses to run without a bridge key; verifies the gateway session is authenticated before
touching any order; every result (fill or failure) is reported back and Slack-notified server-side.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

import ibkr

BASE = (os.environ.get("ARTIK_BASE") or "http://localhost:8100").rstrip("/")
KEY = os.environ.get("TRADING_BRIDGE_KEY", "")
POLL_SECONDS = int(os.environ.get("BRIDGE_POLL_SECONDS", "15"))


def _api(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"X-Bridge-Key": KEY, "Content-Type": "application/json"},
        method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _execute(cl: ibkr.IBKRClient, order: dict) -> tuple[str, object]:
    """Place one approved order through the local gateway. Returns (status, result)."""
    acct = (order.get("account_id") or "").strip()
    if not acct:
        return ("failed", "order has no IBKR account_id (set it in Agent Settings)")
    conid = cl.conid_for(order["ticker"], order.get("sec_type") or "STK")
    if not conid:
        return ("failed", f"no IBKR contract found for {order['ticker']}")
    payload = {"conid": int(conid), "orderType": order.get("order_type") or "MKT",
               "side": order["side"], "quantity": float(order["qty"]),
               "tif": order.get("tif") or "DAY"}
    res = cl.place_order(acct, payload)
    # IBKR often responds with confirmation prompts (precautionary warnings) — confirm them.
    for _ in range(4):
        prompts = [x for x in (res or []) if isinstance(x, dict) and x.get("id") and x.get("message")]
        if not prompts:
            break
        res = cl.reply(prompts[0]["id"], True)
    return ("submitted", res)


def run_once(cl: ibkr.IBKRClient) -> int:
    try:
        auth = cl.auth_status()
    except Exception as e:  # noqa: BLE001
        print(f"[bridge] gateway unreachable ({e}) — start it and log in at https://localhost:5001")
        return 0
    if not auth.get("authenticated"):
        print("[bridge] gateway session not authenticated — re-login at https://localhost:5001; orders stay queued")
        return 0
    try:
        orders = _api("/api/trading/bridge/orders").get("orders") or []
    except Exception as e:  # noqa: BLE001
        print(f"[bridge] server poll failed: {e}")
        return 0
    done = 0
    for o in orders:
        print(f"[bridge] executing {o['side']} {o['qty']} {o['ticker']} (order {o['id']})…")
        try:
            status, result = _execute(cl, o)
        except Exception as e:  # noqa: BLE001
            status, result = "failed", str(e)
        try:
            _api("/api/trading/bridge/result",
                 {"id": o["id"], "status": status,
                  "result": result if isinstance(result, (dict, list, str)) else str(result)})
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] result report failed for {o['id']}: {e}")
        print(f"[bridge]   → {status}")
        done += 1
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="Trading Desk → IBKR gateway execution bridge")
    ap.add_argument("--once", action="store_true", help="single pass instead of the poll loop")
    args = ap.parse_args()
    if not KEY:
        sys.exit("TRADING_BRIDGE_KEY is not set — refusing to run.")
    cl = ibkr.IBKRClient()
    if not cl.configured:
        sys.exit("IBKR_BASE_URL is not set — point it at the local Client Portal Gateway.")
    print(f"[bridge] artikBroker={BASE}  gateway={os.environ.get('IBKR_BASE_URL')}  poll={POLL_SECONDS}s")
    if args.once:
        run_once(cl)
        return
    while True:
        try:
            run_once(cl)
        except Exception as e:  # noqa: BLE001 — the loop must survive anything
            print(f"[bridge] pass failed: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
