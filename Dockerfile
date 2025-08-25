# ---------- Frontend build ----------
FROM node:20-alpine AS frontend
WORKDIR /app
COPY ./frontend/package*.json ./
RUN npm ci
COPY ./frontend/ ./frontend
WORKDIR /app/frontend
RUN NODE_OPTIONS=--max_old_space_size=8192 npm run build   # Vite → /app/frontend/dist

# ---------- Python runtime (Debian slim) ----------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg curl build-essential libffi-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Python deps zuerst (Cache)
COPY requirements.txt .
# (optional) neuere pip hilft bei resolvern
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# App-Code
COPY . .
# Frontend-Build in dein static-Verzeichnis legen
COPY --from=frontend /app/static/ ./static/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# Quart via ASGI-Worker; wir verwenden ein kleines server.py als Target
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","-c","gunicorn.conf.py","server:app","--bind","0.0.0.0:8000","--access-logfile","-","--error-logfile","-"]
