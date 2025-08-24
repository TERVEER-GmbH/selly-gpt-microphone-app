# ---------- Frontend Build ----------
FROM node:20-alpine AS frontend
WORKDIR /app
COPY ./frontend/package*.json ./
RUN npm ci
COPY ./frontend/ ./frontend
# Passe das an, falls dein Build anders heißt (z.B. "build")
WORKDIR /app/frontend
RUN NODE_OPTIONS=--max_old_space_size=8192 npm run build

# ---------- Python Runtime ----------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Systempakete (build + runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libffi-dev \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Python-Deps
WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code + Static
COPY . .
# WICHTIG: kopiere das gebaute Frontend in dein "static" Verzeichnis,
# so wie es deine Quart-App erwartet (du nutzt static_url_path="").
# Häufiger Build-Pfad ist "dist" (Vite) oder "build" (CRA).
COPY --from=frontend /app/frontend/dist/ ./static/

# Healthcheck (optional, hilft lokal & bei Orchestrierung)
EXPOSE 8000
#HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# Quart braucht ASGI-Worker:
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","server:app","--bind","0.0.0.0:8000","--access-logfile","-","--error-logfile","-"]
