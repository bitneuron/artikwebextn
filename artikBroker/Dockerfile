# artikBroker — FastAPI (SPA + /api/*) + the artik_engine scoring package.
# BUILD FROM THE SUPERPROJECT ROOT so both folders are in context:
#   docker build -f artikBroker/Dockerfile -t artikbroker:latest .
FROM python:3.13-slim

# Faster, quieter Python; unbuffered logs for App Runner
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 0) Litestream: streams the SQLite users DB to S3 so accounts survive redeploys.
ARG LITESTREAM_VERSION=0.3.13
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget \
 && wget -qO /tmp/ls.tar.gz "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
 && tar -C /usr/local/bin -xzf /tmp/ls.tar.gz litestream \
 && rm /tmp/ls.tar.gz \
 && apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 1) Pinned web + scientific deps (cached layer — changes rarely)
COPY artikBroker/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# 2) The scoring engine package (deps already satisfied above -> --no-deps)
COPY artikAgents/agents/stock_broker_agent/pyproject.toml /tmp/engine/pyproject.toml
COPY artikAgents/agents/stock_broker_agent/artik_engine /tmp/engine/artik_engine
RUN pip install --no-deps /tmp/engine

# 3) The app itself
COPY artikBroker/ /app/
# Never ship local dev runtime state — these are created fresh at runtime. (Belt &
# suspenders alongside .dockerignore; guarantees prod bootstraps a clean users DB.)
RUN rm -rf /app/config /app/cache /app/search_history

# 4) Stock-analysis methodology skills (read/edited by Skills Management).
#    SKILLS_DIR points the app at this baked-in copy. NOTE: like the users DB, edits
#    here are on the container FS and reset on redeploy until backed by a volume.
COPY artikAgents/agents/knowledge_bases/stock_analysis/skills /app/skills_library
ENV SKILLS_DIR=/app/skills_library

# ArtikFinance: bundled personal-financial-statement workbook (imported into the DB at startup;
# the DB — Litestream-replicated — is the runtime source, the workbook is import-only).
COPY ["artikAgents/agents/knowledge_bases/personal_financial_statement/Financial Statement.xlsx", "/app/finance_kb/Financial Statement.xlsx"]

# LLM model versions — single source of truth (env vars can override at runtime).
COPY artikAgents/agents/shared/models.json /app/models.json

# 5) News Collector agent — the Broker runs it as a subprocess. Bake it in and point
#    the app at it (deps: anthropic + yfinance, already installed above; PyYAML optional).
COPY artikAgents/agents/news_collector_agent /opt/news_collector_agent
RUN rm -rf /opt/news_collector_agent/__pycache__ /opt/news_collector_agent/data/news_collector
ENV NEWS_COLLECTOR_DIR=/opt/news_collector_agent \
    NEWS_COLLECTOR_DATA_DIR=/app/data/news_collector

# 6) Persistent users DB (Litestream-backed). The DB lives at /data/users.db (outside
#    /app/config, which is wiped above); Litestream restores/replicates it to S3.
COPY artikBroker/litestream.yml /etc/litestream.yml
COPY artikBroker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data
ENV USERS_DB_PATH=/data/users.db \
    LITESTREAM_DB=/data/users.db

# App Runner sends traffic to $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080
CMD ["/usr/local/bin/docker-entrypoint.sh"]
