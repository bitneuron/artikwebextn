# artikAgentFactory — single-image deploy: FastAPI API + built React SPA + worker CMD
# (branched via WORKER_ROLE at runtime — see docker-entrypoint.sh). One immutable
# image is built once in CI and promoted from staging to production, never rebuilt
# per environment (see infra/README.md and the GitHub Actions workflow).
# Build from the artikAgentFactory/ root: docker build -t artikagentfactory .

# ── stage 1: build the frontend ──────────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# VITE_API_URL left blank -> the SPA calls the API at the same origin (/api/*)
RUN npm run build

# ── stage 2: backend + the built SPA ─────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./frontend_dist
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV ENVIRONMENT=production PORT=8420

EXPOSE 8420
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8420/api/health || exit 1

CMD ["/usr/local/bin/docker-entrypoint.sh"]
