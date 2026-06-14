# Deploying artikBroker to AWS App Runner

artikBroker is a self-contained FastAPI service (SPA + `/api/*` + the `artik_engine`
scoring package; only external call is Yahoo Finance). App Runner runs it as a
container with HTTPS, autoscaling, and a 35s-friendly request timeout — no Lambda /
API Gateway 29s limit, no cold starts.

## What gets deployed
- **AI Search** (natural language) + **Analyze** (symbols) + **S&P 500 / DOW** — public market data.
- **Portfolio** tab shows empty: the private CSVs are deliberately **not** in the
  image (`.dockerignore` excludes `knowledge_bases/`), so no financial data is hosted.

## AI Search + password gate (env vars)
- **AI Search** (`/api/search`) calls Claude to parse the query, then the engine scores
  candidates. It needs **`ANTHROPIC_API_KEY`** at runtime (read from env on AWS, or
  `artikAgents/.env` locally). Without it, AI Search returns a clear "disabled" message;
  ticker analysis still works.
- Because the LLM endpoint is public, protect the app with **`APP_PASSWORD`** — `deploy.sh` stores it as a pbkdf2
  HASH (`APP_PASSWORD_HASH`) plus a random `APP_SECRET` for signing session cookies;
  the plaintext never leaves your shell. Users sign in at `/login`; later requests use
  a signed HttpOnly+Secure cookie. Unset locally → open for dev.
- The key is **never baked into the image** — `deploy.sh` passes both as App Runner
  RuntimeEnvironmentVariables. (For stricter handling, move them to Secrets Manager later.)

## Prerequisites
- Docker Desktop running (`open -a Docker`, wait for it to start).
- AWS CLI authenticated (`aws sts get-caller-identity` works). Region defaults to
  `us-west-2` (override with `AWS_REGION`).

## Deploy (one command, from the superproject root)
```bash
# Password-gated + AI Search enabled (recommended for the public deploy):
APP_PASSWORD='choose-a-strong-pass' ./artikBroker/deploy.sh
```
`ANTHROPIC_API_KEY` is auto-read from `artikAgents/.env` if not in your shell.
This builds the image, pushes it to ECR, ensures the App Runner ECR-access role,
creates the service (or updates image + env vars if it exists), and prints the HTTPS URL.
First creation takes ~5–10 min to reach RUNNING; the browser will prompt for the
username (`artik`) and your `APP_PASSWORD`.

> AI Search requires credits on the Anthropic account tied to the key.

## Redeploy after code changes
Now that secrets live in Secrets Manager, ship code changes with `./artikBroker/redeploy.sh`
(builds + pushes an immutable tag and swaps ONLY the image, preserving the Secrets
Manager refs + IAM roles). `deploy.sh` is for the initial plaintext-env setup only.

## Test the image locally first (optional but recommended)
```bash
docker build -f artikBroker/Dockerfile -t artikbroker .      # from repo root
docker run --rm -p 8080:8080 artikbroker
curl "http://localhost:8080/api/analyze?symbols=NVDA"        # in another shell
```

## Notes
- Instance: 1 vCPU / 2 GB (enough for pandas/numpy/yfinance). Adjust in `deploy.sh`.
- The daily index cache lives on the instance filesystem (ephemeral) — it simply
  recomputes after a redeploy/scale event. For cross-instance caching, point it at S3.
- Custom domain & TLS: add via the App Runner console → Custom domains.
- Cost: App Runner bills for the running instance (~$5–25/mo at this size); pause the
  service when idle to avoid charges.
