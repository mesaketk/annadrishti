# syntax=docker/dockerfile:1
# Build from the PROJECT ROOT:  docker build -f deploy/Dockerfile -t annadrishti .

# ---- stage 1: build the React frontend --------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
RUN npm install -g pnpm@10 --no-fund --no-audit
COPY web/package.json web/pnpm-lock.yaml* web/package-lock.json* ./
# prefer the lockfile that exists: pnpm, then npm ci, then plain npm install
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then npm ci; \
    else npm install; fi
COPY web/ ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm run build; else npm run build; fi

# ---- stage 2: API + static frontend -----------------------------------------
FROM python:3.11-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PORT=8080 ARTIFACTS_DIR=/app/artifacts WEB_DIST_DIR=/app/web/dist
WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install -r api/requirements.txt
COPY api/ api/
# districts.json, kpis.json, timeseries/ only (see .dockerignore)
COPY artifacts/ artifacts/
COPY --from=web /web/dist web/dist
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
