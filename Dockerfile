# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Build the React/Vite frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend

# Install dependencies first (better layer caching)
COPY frontend/package*.json ./
RUN npm ci

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Django / Python application
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Prevent Python from writing pyc files; keep stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS dependencies for psycopg (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Copy project source and built frontend, setting owner to appuser
COPY --chown=appuser:appgroup . .
COPY --chown=appuser:appgroup --from=frontend-build /app/frontend/dist ./frontend/dist

# Collect static files (runs without a real DB; uses empty FIELD_ENCRYPTION_KEY placeholder)
RUN DJANGO_SETTINGS_MODULE=emr.settings \
    SECRET_KEY=build-placeholder \
    DATABASE_URL=sqlite:////tmp/build.db \
    FIELD_ENCRYPTION_KEY=YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE= \
    python manage.py collectstatic --noinput

# Copy & enable the entrypoint
COPY --chown=appuser:appgroup entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
