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

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./frontend_dist

RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/artik_notifier.db \
    ENVIRONMENT=production \
    PORT=8080

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/api/health').status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
