# Artik Broker — Interactive Brokers (IBKR) Brokerage

_Submitted 2026-07-05. Implemented in commits `c5d55d5` (client + endpoints + UI + trading) and
`d1e7700` (OAuth 1.0a path). Third brokerage alongside E*TRADE + Schwab. See [memory: etrade-integration]._

---

> now create another brokerage account similar to etrade and charles schwab. Create a left menu
> for IBKR and this is their API documentation. connect with IBKR to do buy/sell/view stocks, etf
> and crypto

Follow-up:
> yes. user my username and password that i gave  → (clarified: IBKR's API never takes a raw
> username/password inside the app; E*TRADE login ≠ IBKR)
> do no 2  → build the OAuth 1.0a hosted Web API auth path

---

## Delivered
Mirror the E*TRADE / Schwab pattern: a 🧭 **IBKR left-menu item** (admin-only), connect / view
accounts + holdings / **Analyze Portfolio** (scored live via the shared engine, `portfolio_store`
source=`ibkr`, no tokens stored), and a **Trade panel** to **buy/sell stocks · ETF · crypto**
(side, symbol, secType STK/CRYPTO, qty, MKT/LMT, TIF, live Quote, confirm-before-submit + IBKR's
order reply/confirm flow). All `/api/ibkr/*` endpoints are **admin-only** (RBAC gate). Portfolio
source dropdown gains "Interactive Brokers".

Built to IBKR's **Client Portal Web API** (REST). Two authentication paths, one shared client + UI:

1. **Client Portal Gateway** (`ibkr.py`): the user runs IBKR's gateway (reachable from AWS) and
   logs in via IBKR SSO on the gateway's own page; the app calls the gateway's REST base
   (`IBKR_BASE_URL`). The gateway holds the session — the app stores no IBKR credentials/tokens.
   Env: `IBKR_BASE_URL`, `IBKR_GATEWAY_URL`, `IBKR_VERIFY_SSL`, `IBKR_ENV`.

2. **OAuth 1.0a hosted Web API** (`ibkr_oauth.py`, no gateway): negotiates a Live Session Token via
   a Diffie-Hellman exchange signed RSA-SHA256, verifies it against IBKR's signature, then signs
   every request HMAC-SHA256; `ssodh_init` opens the brokerage session. Env
   `IBKR_OAUTH_CONSUMER_KEY / ACCESS_TOKEN / ACCESS_TOKEN_SECRET / SIGNATURE_KEY / ENCRYPTION_KEY /
   DH_PRIME` (PEMs inline or `*_FILE`). When configured (and no gateway base set), the client
   auto-switches to OAuth mode (api.ibkr.com, signed headers, real TLS).

## Security / constraints
- IBKR never accepts a raw username/password inside the app — auth is gateway SSO or OAuth keys.
- All secrets env-only, never committed, never sent to the client. Trading is admin-only + explicit
  confirm. Snapshots store holdings/totals only (no tokens). `cryptography` pinned for the OAuth math.

## Activation (user action required)
- Gateway: run it, then set `IBKR_BASE_URL`/`IBKR_GATEWAY_URL` and Refresh in the IBKR tab.
- OAuth: from IBKR self-service, set the `IBKR_OAUTH_*` env vars, then "Initialize IBKR session".
Until configured it shows "not configured" and degrades gracefully. Tests: `test_ibkr.py`(6) +
`test_ibkr_oauth.py`(5); broker suite 63 pass. The live DH/LST handshake needs real IBKR OAuth keys
to verify end-to-end (request-signing is unit-tested).
