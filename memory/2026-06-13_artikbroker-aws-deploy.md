# artikBroker — AWS deployment (2026-06-13)

artikBroker is deployed to **AWS App Runner** (container), live at
**https://hpzkeypha3.us-west-2.awsapprunner.com**.

## Why App Runner (not Amplify)
artikBroker is a self-contained Python FastAPI app (SPA + `/api/*` + bundled
`artik_engine`; only external call is Yahoo Finance). Amplify Hosting is for JS
frontends + Lambda/API-Gateway, and API Gateway's **29s timeout would break the
~35s `/api/index` (S&P/DOW) scan** plus heavy cold starts. App Runner runs the
container as-is: HTTPS, autoscale, long-request friendly, no infra to manage.
User's stated criteria: "easy to deploy and stable."

## AWS resources (account 515966528039, region us-west-2)
- ECR repo `artikbroker` (image pushed; auto-deploy on new `:latest`)
- App Runner service `artikbroker` — 1 vCPU / 2 GB, port 8080, ~$5-25/mo running (pausable)
- IAM role `AppRunnerECRAccessRole` (ECR pull). NOTE: deployed using AWS **root** creds —
  create an IAM user/role for future deploys.

## Deploy / redeploy
- One command from repo root: `./artikBroker/deploy.sh` (build → ECR → App Runner).
- Runbook: `artikBroker/DEPLOY.md`. Dockerfile builds from the **superproject root**
  (needs both `artikBroker/` and the engine at `artikAgents/agents/stock_broker_agent/`).
- Deps pinned in `artikBroker/requirements.txt` (Py 3.13, numpy 2.4.0, pandas 2.3.3…).

## AI Search + password gate (added 2026-06-14)
- `/api/search`: natural-language stock discovery. Provider cascade — **Claude
  (claude-opus-4-8) first, auto-fallback to OpenAI (gpt-5-mini)** on any failure
  (e.g. Anthropic low credits). LLM only parses intent + proposes candidate tickers;
  the engine produces all scores. UI banner shows which provider answered.
- **Live behind HTTP Basic auth** (username `artik`; password in the `APP_PASSWORD`
  App Runner env var — value NOT stored here). Also requires `ANTHROPIC_API_KEY` +
  `OPENAI_API_KEY` env vars (set by deploy.sh from artikAgents/.env; never in the image).
- **Gotchas learned:** (1) the container installs only `requirements.txt` — both
  `anthropic` AND `openai` must be listed there (local venv masked the missing openai).
  (2) **AutoDeployments is now DISABLED** — it raced with update-service and served stale
  revisions. Deploy with an **immutable image tag** (`v<timestamp>`) via update-service,
  not `:latest`.

## Scope decisions
- **One service only** (artikBroker; not artikAPIs). It's self-contained.
- **Public, no Portfolio:** `.dockerignore` excludes `knowledge_bases/`, so the private
  Stock_Portfolio CSVs are NOT in the image — Portfolio tab is empty on AWS, no auth needed.
  To host the portfolio later: add auth (Cognito/password) + store CSVs in private S3.
- Index daily cache is on ephemeral instance FS (recomputes after redeploy) — move to S3
  if cross-instance caching is needed.

## Related
- App design: [[2026-06-13_artik-broker-webapp]]. Engine: [[2026-06-13_scoring-engine-business-logic]].
