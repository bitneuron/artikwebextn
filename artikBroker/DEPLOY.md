# Deploying artikBroker to AWS App Runner

artikBroker is a self-contained FastAPI service (SPA + `/api/*` + the `artik_engine`
scoring package; only external call is Yahoo Finance). App Runner runs it as a
container with HTTPS, autoscaling, and a 35s-friendly request timeout — no Lambda /
API Gateway 29s limit, no cold starts.

## What gets deployed
- **Analyze** (any symbols) and **S&P 500 / DOW** tabs — all public market data.
- **Portfolio** tab shows empty: the private CSVs are deliberately **not** in the
  image (`.dockerignore` excludes `knowledge_bases/`), so no financial data is hosted.

## Prerequisites
- Docker Desktop running (`open -a Docker`, wait for it to start).
- AWS CLI authenticated (`aws sts get-caller-identity` works). Region defaults to
  `us-west-2` (override with `AWS_REGION`).

## Deploy (one command, from the superproject root)
```bash
./artikBroker/deploy.sh
```
This builds the image, pushes it to ECR, ensures the App Runner ECR-access role,
creates the service (or redeploys if it exists), and prints the HTTPS URL.
First creation takes ~5–10 min to reach RUNNING.

## Redeploy after code changes
Re-run the same command — App Runner auto-deploys the new `:latest` image.

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
