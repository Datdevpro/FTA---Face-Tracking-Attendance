#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Project settings must come from .env, not inherited shell variables.
unset DEBUG FACE_ONNX_PROVIDER ANTI_SPOOFING_PROVIDER || true

on_error() {
    local exit_code=$?
    echo
    echo "[ERROR] Setup failed near line ${BASH_LINENO[0]}."
    echo "Fix the error shown above, then run this script again."
    exit "$exit_code"
}
trap on_error ERR

echo "============================================================"
echo "  FTA - Automatic Setup for Ubuntu"
echo "============================================================"
echo

if [[ ! -r /etc/os-release ]]; then
    echo "[ERROR] Cannot identify this operating system."
    exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "[ERROR] This installer supports Ubuntu only. Detected: ${PRETTY_NAME:-unknown}"
    exit 1
fi

echo "[1/8] Detected ${PRETTY_NAME}."

if [[ $EUID -eq 0 ]]; then
    APT=(apt-get)
elif command -v sudo >/dev/null 2>&1; then
    APT=(sudo apt-get)
else
    echo "[ERROR] sudo is required to install Ubuntu system packages."
    exit 1
fi

echo "[2/8] Installing Ubuntu system packages..."
"${APT[@]}" update
"${APT[@]}" install -y \
    build-essential \
    ca-certificates \
    curl \
    git \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv

PYTHON_BIN="$(command -v python3)"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'; then
    echo "[ERROR] FTA requires Python 3.10, 3.11, or 3.12."
    echo "This system provides: $($PYTHON_BIN --version 2>&1)"
    exit 1
fi

echo "[3/8] Using $($PYTHON_BIN --version 2>&1)."

if [[ -x venv/bin/python ]]; then
    if ! venv/bin/python -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'; then
        echo "[ERROR] The existing venv uses an unsupported Python version."
        echo "Rename or remove the venv directory, then run this script again."
        exit 1
    fi
    echo "[4/8] Existing virtual environment found."
elif [[ -e venv ]]; then
    echo "[ERROR] The existing venv is not a Linux virtual environment."
    echo "Rename or remove the venv directory, then run this script again."
    exit 1
else
    echo "[4/8] Creating virtual environment..."
    "$PYTHON_BIN" -m venv venv
fi

VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

if [[ -f .env ]]; then
    echo "[5/8] Existing .env configuration preserved."
else
    if [[ ! -f .env.example ]]; then
        echo "[ERROR] .env.example is missing."
        exit 1
    fi

    cp .env.example .env
    "$VENV_PYTHON" -c "from pathlib import Path; import secrets; p=Path('.env'); text=p.read_text(encoding='utf-8'); text=text.replace('JWT_SECRET_KEY=your-super-secret-key-change-this-in-production', 'JWT_SECRET_KEY=' + secrets.token_hex(32)); p.write_text(text, encoding='utf-8')"
    echo "[5/8] Created .env with CPU inference and a random JWT secret."
fi

echo "[6/8] Installing Python dependencies. This can take several minutes..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel cython

# The bundled InsightFace wheel is Windows-only. Ubuntu builds InsightFace
# against the local Python version using the compiler packages installed above.
"$VENV_PYTHON" -m pip install --prefer-binary -r requirements.txt
"$VENV_PYTHON" -m pip check

ANTI_SPOOF_MODEL="data/models/anti_spoofing/AntiSpoofing_bin_1.5_128.onnx"
if [[ ! -f "$ANTI_SPOOF_MODEL" ]]; then
    echo "[ERROR] Missing anti-spoofing model: $ANTI_SPOOF_MODEL"
    exit 1
fi

echo "[7/8] Creating the SQLite database and default account..."
"$VENV_PYTHON" -m scripts.init_db

echo "[8/8] Preparing the face recognition model..."
echo "      The first download is about 300 MB. Keep Internet connected."
"$VENV_PYTHON" -c "from app.config import settings; from app.services.face_recognition import FaceRecognitionService; service=FaceRecognitionService(settings.FACE_MODEL_NAME, settings.MODELS_DIR, onnx_provider='cpu'); service.initialize(); print('Face recognition model is ready.')"

chmod +x setup-fta-ubuntu.sh

cat <<'EOF'

============================================================
  FTA setup completed successfully.
============================================================

Login:    admin / admin123
Start:    ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Website:  http://localhost:8000

Change the default admin password before using real employee data.
EOF

