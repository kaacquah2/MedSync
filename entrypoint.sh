#!/bin/sh
set -e

# Fail fast if frontend assets are missing in production
if [ "$DEBUG" != "true" ] && [ ! -d "frontend/dist" ]; then
    echo "ERROR: frontend/dist directory missing. Run 'npm run build' inside frontend/ before starting in production mode."
    exit 1
fi

# Migrations should run in a dedicated release/job step before starting web replicas.
# In single-container or dev environments, set RUN_MIGRATIONS=true to run on startup.
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "==> Running database migrations (RUN_MIGRATIONS=true)..."
    python manage.py migrate --noinput
else
    echo "==> Skipping database migrations on startup (RUN_MIGRATIONS not set to 'true'). Run via release/job step."
fi

# Demo seeding is opt-in: set SEED_DEMO=true to populate sample hospitals,
# staff, patients, and encounters. Do NOT enable in production — seed_demo
# creates accounts with publicly-known passwords.
if [ "$SEED_DEMO" = "true" ]; then
    echo "==> Seeding demo data (SEED_DEMO=true)..."
    python manage.py seed_demo
else
    echo "==> Skipping demo seeding (SEED_DEMO not set to 'true')."
fi

echo "==> Starting Gunicorn..."
exec gunicorn emr.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --worker-class gthread \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
