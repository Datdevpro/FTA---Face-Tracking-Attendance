# =======================================================
# FTA - Dockerfile for Windows (Docker Desktop / WSL2)
# =======================================================

# Stage 1: Build virtual environment and dependencies
FROM python:3.11-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MAKEFLAGS=-j4

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        gfortran \
        libopenblas-dev \
        liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt

# InsightFace 0.7.3 builds from source on Linux x86_64, using Cython
RUN pip install --upgrade \
        pip==24.3.1 \
        setuptools==75.3.0 \
        wheel==0.45.1 \
        Cython==3.0.12 \
        numpy==1.26.4 \
    && pip install --no-build-isolation insightface==0.7.3 \
    && pip install --prefer-binary -r /tmp/requirements.txt \
    && pip check

# Stage 2: Minimal runtime image
FROM python:3.11-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}" \
    TZ=Asia/Ho_Chi_Minh \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        liblapack3 \
        libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts

# Copy entrypoint script and ensure Unix line endings
COPY docker-windows/entrypoint.sh /usr/local/bin/fta-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/fta-entrypoint \
    && chmod +x /usr/local/bin/fta-entrypoint \
    && mkdir -p \
        data/face_images \
        data/faiss_index \
        data/models \
        data/snapshots

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/fta-entrypoint"]
