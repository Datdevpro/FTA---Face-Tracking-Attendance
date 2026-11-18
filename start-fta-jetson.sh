#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
PY="$PROJECT_ROOT/.venv-jetson/bin/python"
if [[ ! -x "$PY" ]]; then
    printf 'Run bash setup-fta-jetson.sh first.\n' >&2
    exit 1
fi
# Native CPU runtime. POSIX TZ UTC-7 means Vietnam UTC+07:00.
export FACE_ONNX_PROVIDER=cpu DEBUG=false
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
export TZ="${FTA_TIMEZONE:-UTC-7}"
exec "$PY" - <<'PY'
import uvicorn
from app.config import settings
print(f'FTA: http://localhost:{settings.PORT} (bind {settings.HOST})', flush=True)
print('Use the Jetson IP to access from another computer. Ctrl+C stops the server.', flush=True)
uvicorn.run('app.main:app', host=settings.HOST, port=settings.PORT, workers=1, reload=False)
PY
