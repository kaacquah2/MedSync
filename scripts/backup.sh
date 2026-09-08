#!/usr/bin/env bash
set -euo pipefail

# Lightweight backup script for mEd EMR (Database + Clinical Documents)
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

echo "==> Starting mEd backup at ${TIMESTAMP}..."

# 1. Backup Database
if [ -n "${DATABASE_URL:-}" ]; then
    echo "Dumping PostgreSQL database from DATABASE_URL..."
    pg_dump "$DATABASE_URL" --format=custom --file="${BACKUP_DIR}/db_${TIMESTAMP}.dump"
elif [ -f "db.sqlite3" ]; then
    echo "Backing up SQLite database..."
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 db.sqlite3 ".backup '${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3'"
    else
        cp db.sqlite3 "${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"
    fi
else
    echo "Warning: No DATABASE_URL or db.sqlite3 found. Skipping database dump."
fi

# 2. Backup Clinical Documents
if [ -d "media/patient_documents" ]; then
    echo "Archiving patient documents..."
    tar -czf "${BACKUP_DIR}/documents_${TIMESTAMP}.tar.gz" -C media patient_documents
fi

echo "==> Backup successfully created at ${BACKUP_DIR}"
