#!/usr/bin/env sh

set -eu

cd /app

mkdir -p \
    data/face_images \
    data/faiss_index \
    data/models \
    data/snapshots

# Idempotently create tables, departments, work schedule, and the first admin.
python -m scripts.init_db

exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 1

