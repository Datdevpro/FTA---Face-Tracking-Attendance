#!/usr/bin/env sh
set -eu

cd /app

mkdir -p \
    data/face_images \
    data/faiss_index \
    data/models \
    data/snapshots

# Run database initialization and seed default admin (admin/admin123) idempotently
echo "Initializing database and default data..."
python -m scripts.init_db

echo "Starting FTA application on port ${PORT:-8000}..."
exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 1
