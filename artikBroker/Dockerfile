# artikBroker — FastAPI (SPA + /api/*) + the artik_engine scoring package.
# BUILD FROM THE SUPERPROJECT ROOT so both folders are in context:
#   docker build -f artikBroker/Dockerfile -t artikbroker:latest .
FROM python:3.13-slim

# Faster, quieter Python; unbuffered logs for App Runner
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

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

# 5) News Collector agent — the Broker runs it as a subprocess. Bake it in and point
#    the app at it (deps: anthropic + yfinance, already installed above; PyYAML optional).
COPY artikAgents/agents/news_collector_agent /opt/news_collector_agent
RUN rm -rf /opt/news_collector_agent/__pycache__ /opt/news_collector_agent/data/news_collector
ENV NEWS_COLLECTOR_DIR=/opt/news_collector_agent \
    NEWS_COLLECTOR_DATA_DIR=/app/data/news_collector

# App Runner sends traffic to $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
