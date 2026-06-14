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
- **Ship a code change → `./artikBroker/redeploy.sh`** (the canonical deploy now that secrets
  live in Secrets Manager). It builds an **immutable-tagged** image, pushes to ECR, and updates the
  service swapping **only the image** — preserving `RuntimeEnvironmentSecrets` + IAM roles. Uses the
  **artikAPIs venv python** for the boto3 step (system python3 has no boto3 — that was a bug).
- `./artikBroker/deploy.sh` is the **initial plaintext-env setup only** — it writes env vars directly
  and would REGRESS the Secrets Manager config; don't use it on the live service. (DEPLOY.md is the runbook.)
- Dockerfile builds from the **superproject root** (needs both `artikBroker/` and the engine at
  `artikAgents/agents/stock_broker_agent/`). Deps pinned in `artikBroker/requirements.txt`
  (Py 3.13, numpy 2.4.0, pandas 2.3.3, anthropic, openai…).
- **Live features (image `v2026061401…`):** AI Search (Claude→GPT), login gate, sortable tables,
  Alpha Vantage enrichment. See [[2026-06-13_artik-broker-webapp]] for the feature details.

## AI Search + password gate (added 2026-06-14)
- `/api/search`: natural-language stock discovery. Provider cascade — **Claude
  (claude-opus-4-8) first, auto-fallback to OpenAI (gpt-5-mini)** on any failure
  (e.g. Anthropic low credits). LLM only parses intent + proposes candidate tickers;
  the engine produces all scores. UI banner shows which provider answered.
- **Auth = login form + signed session cookie** (`/login`, `/logout`). Password verified
  against a **pbkdf2-sha256 HASH** (`APP_PASSWORD_HASH`); a random `APP_SECRET` signs an
  HttpOnly+Secure cookie (7-day TTL). No plaintext password stored or sent per-request
  (replaced the earlier HTTP Basic Auth). Also needs `ANTHROPIC_API_KEY` + `OPENAI_API_KEY`
  env vars (deploy.sh sets all from artikAgents/.env; keys never in the image). Auth is off
  locally when those env vars are unset.
- **Gotchas learned:** (1) the container installs only `requirements.txt` — both
  `anthropic` AND `openai` must be listed there (local venv masked the missing openai).
  (2) **AutoDeployments is now DISABLED** — it raced with update-service and served stale
  revisions. Deploy with an **immutable image tag** (`v<timestamp>`) via update-service,
  not `:latest`.

## Secrets in AWS Secrets Manager (2026-06-14)
- All **5** sensitive values — ANTHROPIC_API_KEY, OPENAI_API_KEY, APP_PASSWORD_HASH, APP_SECRET,
  **ALPHA_VANTAGE_API_KEY** — are **Secrets Manager** entries `artikbroker/<KEY>`, referenced by the
  service as `RuntimeEnvironmentSecrets` (ARNs). **No plaintext** in the service config.
- App Runner reads them via an **instance role** `AppRunnerInstanceRole-artikbroker`
  (trust: tasks.apprunner.amazonaws.com; inline policy `ReadArtikbrokerSecrets`:
  secretsmanager:GetSecretValue on all 5 ARNs). Distinct from the ECR *access* role
  `AppRunnerECRAccessRole` (build.apprunner.amazonaws.com) used to pull the image.
- Scripts (idempotent, read values from the gitignored `.env`, never hardcoded):
  `migrate_secrets.py` (the original 4), `add_alpha_vantage_aws.py` (adds a key + updates the role policy).
- Login is **password-gated**: username `artik`, password value lives ONLY in Secrets Manager /
  the user's head (NOT in memory or git). To rotate any value: update the Secrets Manager secret,
  then `aws apprunner start-deployment` (or redeploy).

## Scope decisions
- **One service only** (artikBroker; not artikAPIs). It's self-contained.
- **Public, no Portfolio:** `.dockerignore` excludes `knowledge_bases/`, so the private
  Stock_Portfolio CSVs are NOT in the image — Portfolio tab is empty on AWS, no auth needed.
  To host the portfolio later: add auth (Cognito/password) + store CSVs in private S3.
- Index daily cache is on ephemeral instance FS (recomputes after redeploy) — move to S3
  if cross-instance caching is needed.

## Related
- App design: [[2026-06-13_artik-broker-webapp]]. Engine: [[2026-06-13_scoring-engine-business-logic]].
