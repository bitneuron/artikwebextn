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

# App Runner sends traffic to $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
