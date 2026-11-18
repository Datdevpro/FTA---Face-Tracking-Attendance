#!/usr/bin/env bash

set -Eeuo pipefail

DOCKER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$DOCKER_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

on_error() {
    local exit_code=$?
    echo
    echo "[ERROR] Jetson deployment failed near line ${BASH_LINENO[0]}." >&2
    echo "Review the error above, then run ./docker-ubuntu/deploy.sh again." >&2
    exit "$exit_code"
}
trap on_error ERR

echo "============================================================"
echo "  FTA - Jetson Nano Docker Deployment"
echo "============================================================"
echo

if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "[ERROR] This deployment must be built on an ARM64 Jetson device." >&2
    echo "Detected architecture: $(uname -m)" >&2
    exit 1
fi

if [[ ! -f /etc/nv_tegra_release ]]; then
    echo "[WARNING] /etc/nv_tegra_release was not found."
    echo "          Confirm this device is running NVIDIA JetPack/L4T."
else
    echo "Jetson release: $(head -n 1 /etc/nv_tegra_release)"
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker is not installed." >&2
    echo "Install it with: sudo apt update && sudo apt install -y docker.io docker-compose" >&2
    exit 1
fi

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
else
    DOCKER=(sudo docker)
    "${DOCKER[@]}" info >/dev/null
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
    COMPOSE=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
    if [[ "${DOCKER[0]}" == "sudo" ]]; then
        COMPOSE=(sudo docker-compose)
    else
        COMPOSE=(docker-compose)
    fi
else
    echo "[ERROR] Docker Compose is not installed." >&2
    echo "Install it with: sudo apt install -y docker-compose" >&2
    exit 1
fi

JETSON_ENV="$DOCKER_DIR/.env"
JETSON_ENV_EXAMPLE="$DOCKER_DIR/.env.example"
if [[ ! -f "$JETSON_ENV" ]]; then
    if [[ ! -f "$JETSON_ENV_EXAMPLE" ]]; then
        echo "[ERROR] docker-ubuntu/.env.example is missing." >&2
        exit 1
    fi

    cp "$JETSON_ENV_EXAMPLE" "$JETSON_ENV"
    if command -v openssl >/dev/null 2>&1; then
        JWT_SECRET="$(openssl rand -hex 32)"
    else
        JWT_SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    fi
    sed -i "s/JWT_SECRET_KEY=replace-me-with-a-random-secret/JWT_SECRET_KEY=${JWT_SECRET}/" "$JETSON_ENV"
    echo "Created docker-ubuntu/.env with a random JWT secret."
else
    echo "Existing docker-ubuntu/.env preserved."
fi

CAMERA_DEVICE="${FTA_CAMERA_DEVICE:-/dev/video0}"
export FTA_CAMERA_DEVICE="$CAMERA_DEVICE"
if [[ ! -e "$CAMERA_DEVICE" ]]; then
    echo "[WARNING] Camera device $CAMERA_DEVICE was not found."
    echo "          Mapping /dev/null so the container can still start for RTSP or administration."
    export FTA_CAMERA_DEVICE=/dev/null
fi

AVAILABLE_MB="$(awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo)"
if (( AVAILABLE_MB < 1500 )); then
    echo "[WARNING] Only ${AVAILABLE_MB} MB RAM is currently available."
    echo "          Stop other applications and configure swap before building."
fi

echo
echo "Building the ARM64 image on this Jetson. The first build can take a long time..."
"${COMPOSE[@]}" -f "$DOCKER_DIR/docker-compose.yml" build

echo
echo "Starting FTA..."
"${COMPOSE[@]}" -f "$DOCKER_DIR/docker-compose.yml" up -d

echo
echo "Container status:"
"${COMPOSE[@]}" -f "$DOCKER_DIR/docker-compose.yml" ps

JETSON_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

============================================================
  FTA is starting on Jetson Nano.
============================================================

Local URL:    http://localhost:8000
Network URL:  http://${JETSON_IP:-JETSON_IP}:8000
Health:       http://${JETSON_IP:-JETSON_IP}:8000/api/health
Login:        admin / admin123

The first startup may download the buffalo_l model (about 300 MB).
Follow startup logs with:

  ${COMPOSE[*]} -f docker-ubuntu/docker-compose.yml logs -f fta

Stop FTA with:

  ${COMPOSE[*]} -f docker-ubuntu/docker-compose.yml down

Change the default admin password before storing real employee data.
EOF
