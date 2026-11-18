#!/usr/bin/env bash
# Native ARM64 setup: bash setup-fta-jetson.sh [--start]
# Optional: FTA_BUILD_JOBS=1 bash setup-fta-jetson.sh
set -Eeuo pipefail
umask 077
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
info() { printf '\n[FTA] %s\n' "$*"; }
die() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }
trap 'printf "\n[ERROR] Setup stopped at line %s (exit %s). Fix the error and rerun.\n" "$LINENO" "$?" >&2' ERR
START=false
case "${1:-}" in
    --help) head -n 3 "$0"; exit 0 ;;
    --start) START=true ;;
    '') ;;
    *) die "Use: bash setup-fta-jetson.sh [--start|--help]" ;;
esac
(( $# <= 1 )) || die "Too many arguments."
[[ "$(uname -s)" == Linux && "$(uname -m)" == aarch64 ]] || die "Run on the Jetson itself: Linux ARM64 (aarch64)."
(( EUID != 0 )) || die "Run as your normal user, without sudo. The script requests sudo for apt packages."
command -v sudo >/dev/null || die "sudo is required for system packages."
[[ -r /etc/os-release ]] || die "Cannot identify the operating system."
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
    *ubuntu*|*debian*) ;;
    *) die "A Debian/Ubuntu based ARM64 system is required." ;;
esac
GLIBC_VERSION="$(getconf GNU_LIBC_VERSION | awk '{print $2}')"
dpkg --compare-versions "$GLIBC_VERSION" ge 2.27 || die "glibc 2.27+ is required; found $GLIBC_VERSION."
for required in .env.example requirements-jetson.txt start-fta-jetson.sh \
    app/main.py scripts/init_db.py frontend/index.html; do
    [[ -s "$required" ]] || die "Missing $required. Copy the complete FTA source to this device."
done
JOBS="${FTA_BUILD_JOBS:-1}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "FTA_BUILD_JOBS must be a positive integer."
export MAKEFLAGS="-j$JOBS" CMAKE_BUILD_PARALLEL_LEVEL="$JOBS"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export FACE_ONNX_PROVIDER=cpu DEBUG=false
export TZ="${FTA_TIMEZONE:-UTC-7}"
info "Native installation on ${PRETTY_NAME:-Linux}, glibc $GLIBC_VERSION; CPU inference."
free -h
df -h "$PROJECT_ROOT"
info "Installing compiler, Python build prerequisites and camera tools..."
sudo apt-get update
sudo apt-get install -y build-essential pkg-config ca-certificates curl xz-utils \
    python3 python3-venv python3-dev libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncursesw5-dev \
    libgdbm-dev uuid-dev libjpeg-dev libopenblas-dev liblapack-dev libgomp1 v4l-utils

# Keep JetPack's system Python unchanged. Reuse only a working Python 3.10.
PYTHON_VERSION=3.10.21
PREFIX="$PROJECT_ROOT/.jetson-python/$PYTHON_VERSION"
PYTHON_BIN=""
for candidate in "$PREFIX/bin/python3.10" python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
        'import sys, ssl, sqlite3, bz2, lzma, ctypes, venv; assert sys.version_info[:2] == (3, 10); assert ssl.OPENSSL_VERSION_INFO >= (1, 1, 1)' >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    info "Building private Python $PYTHON_VERSION. This may take a long time on Nano."
    BUILD_ROOT="$PROJECT_ROOT/.jetson-build"
    mkdir -p "$BUILD_ROOT" "$PREFIX"
    ARCHIVE="$BUILD_ROOT/Python-$PYTHON_VERSION.tar.xz"
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
        "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tar.xz" -o "$ARCHIVE"
    tar -xJf "$ARCHIVE" -C "$BUILD_ROOT"
    (
        cd "$BUILD_ROOT/Python-$PYTHON_VERSION"
        ./configure --prefix="$PREFIX" --with-ensurepip=install
        make -j "$JOBS"
        make altinstall
    )
    PYTHON_BIN="$PREFIX/bin/python3.10"
fi
"$PYTHON_BIN" -c 'import sys, ssl, sqlite3, bz2, lzma, ctypes; assert sys.version_info[:2] == (3, 10); print(sys.version); print(ssl.OPENSSL_VERSION)'
VENV_DIR="$PROJECT_ROOT/.venv-jetson"
if [[ -e "$VENV_DIR" ]]; then
    [[ -x "$VENV_DIR/bin/python" ]] || die "Existing .venv-jetson is invalid. Rename it and rerun; it will not be deleted automatically."
    "$VENV_DIR/bin/python" -c 'import sys, platform; assert sys.version_info[:2] == (3, 10); assert platform.machine() == "aarch64"' \
        || die "Existing .venv-jetson needs Linux ARM64 Python 3.10. Rename it and rerun."
else
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python"
info "Installing ARM64 CPU dependencies into .venv-jetson..."
"$PY" -m pip install --upgrade pip==24.3.1 setuptools==75.3.0 wheel==0.45.1 Cython==0.29.36 numpy==1.26.4
# Require wheels for native libraries; InsightFace and pure-Python srt use source.
"$PY" -m pip install --no-build-isolation --only-binary=:all: --no-binary=insightface,srt \
    -r requirements-jetson.txt
"$PY" -m pip check
"$PY" -c 'import cv2, faiss, insightface, onnxruntime as ort; assert "CPUExecutionProvider" in ort.get_available_providers(); print("Imports OK; providers:", ort.get_available_providers())'

info "Preparing root .env; backing up existing configuration before changes..."
if [[ ! -f .env ]]; then
    cp .env.example .env
fi
"$PY" - <<'PY'
from pathlib import Path
import re
import secrets
import tempfile
from dotenv import dotenv_values
path = Path('.env')
original = path.read_text(encoding='utf-8-sig')
text = original
values = dotenv_values(path)
updates = {'FACE_ONNX_PROVIDER': 'cpu', 'DEBUG': 'false'}
samples = {'', 'replace-me-with-a-random-secret', 'your-super-secret-key-change-this-in-production', 'fta-dev-secret-key-change-in-production'}
if (values.get('JWT_SECRET_KEY') or '') in samples:
    updates['JWT_SECRET_KEY'] = secrets.token_hex(32)
for key, value in updates.items():
    pattern = r'(?m)^(?:export\s+)?' + re.escape(key) + r'\s*=.*$'
    replacement = key + '=' + value
    if re.search(pattern, text):
        text = re.sub(pattern, replacement, text)
    else:
        text = text.rstrip() + '\n' + replacement + '\n'
if text != original:
    with tempfile.NamedTemporaryFile(prefix='.env.before-jetson-', dir='.', delete=False) as backup:
        backup.write(path.read_bytes())
        print('Config backup:', backup.name)
    path.write_text(text, encoding='utf-8')
PY
chmod 600 .env
info "Checking settings and database connection..."
"$PY" -c 'from app.config import settings; settings.ensure_directories(); from app.core.database import engine; connection=engine.connect(); connection.close(); print("Database connection OK")'
"$PY" -m scripts.init_db
info "Preparing InsightFace model (first run needs Internet)..."
"$PY" - <<'PY'
from app.config import settings
from app.services.face_recognition import FaceRecognitionService
service = FaceRecognitionService(settings.FACE_MODEL_NAME, settings.MODELS_DIR, onnx_provider='cpu')
service.initialize()
assert service.is_initialized and service.active_provider == 'CPUExecutionProvider'
print('Face model ready on CPU')
PY
chmod +x start-fta-jetson.sh
info "Setup complete. Models loaded successfully; camera and attendance still need a live test."
printf 'Start: bash start-fta-jetson.sh\nConfig: %s/.env\n' "$PROJECT_ROOT"
printf 'Default login for a new database: admin / admin123 (change the password).\n'
printf 'USB cameras: v4l2-ctl --list-devices\n'
printf 'For USB use CAMERA_SOURCE=0; for RTSP set its URL in .env.\n'
printf 'Runtime time zone: %s; verify the host clock is correct.\n' "$TZ"
if [[ "$START" == true ]]; then
    exec bash "$PROJECT_ROOT/start-fta-jetson.sh"
fi
