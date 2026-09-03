#!/usr/bin/env sh

set -eu

cd /app

mkdir -p \
    data/face_images \
    data/faiss_index \
    data/models \
    data/snapshots

if [ ! -f data/models/anti_spoofing/AntiSpoofing_bin_1.5_128.onnx ]; then
    echo "ERROR: anti-spoofing model is missing from /app/data/models/anti_spoofing" >&2
    exit 1
fi

# Idempotently create tables, departments, work schedule, and the first admin.
python -m scripts.init_db

exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 1

