# Artik Notifier — single-image deploy: FastAPI API + built React SPA.
# Build from the artikNotifier/ root:  docker build -f Dockerfile -t artik-notifier .

# ── stage 1: build the frontend ──────────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# VITE_API_URL left blank → the SPA calls the API at the same origin (/api/*)
RUN npm run build

# ── stage 2: backend + the built SPA ─────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Litestream: streams the SQLite DB to S3 so data survives App Runner redeploys.
ARG LITESTREAM_VERSION=0.3.13
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget \
 && wget -qO /tmp/ls.tar.gz "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
 && tar -C /usr/local/bin -xzf /tmp/ls.tar.gz litestream \
 && rm /tmp/ls.tar.gz \
 && apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./frontend_dist
COPY litestream.yml /etc/litestream.yml
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/artik_notifier.db \
    LITESTREAM_DB=/data/artik_notifier.db \
    ENVIRONMENT=production \
    PORT=8080

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/api/health').status==200 else 1)"

CMD ["/usr/local/bin/docker-entrypoint.sh"]
