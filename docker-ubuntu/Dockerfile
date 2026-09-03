FROM python:3.10-slim-bullseye AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MAKEFLAGS=-j2 \
    CMAKE_BUILD_PARALLEL_LEVEL=2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        libjpeg62-turbo-dev \
        liblapack-dev \
        libopenblas-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY docker-ubuntu/requirements.txt /tmp/requirements-jetson.txt

# InsightFace 0.7.3 has no Linux ARM64 wheel, so build it once in this stage.
RUN pip install --upgrade \
        pip==24.3.1 \
        setuptools==75.3.0 \
        wheel==0.45.1 \
        Cython==0.29.36 \
        numpy==1.26.4 \
    && pip install --no-build-isolation insightface==0.7.3 \
    && pip install --prefer-binary -r /tmp/requirements-jetson.txt \
    && pip check


FROM python:3.10-slim-bullseye AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        liblapack3 \
        libopenblas0 \
        v4l-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts
COPY data/models/anti_spoofing/AntiSpoofing_bin_1.5_128.onnx \
    ./data/models/anti_spoofing/AntiSpoofing_bin_1.5_128.onnx
COPY docker-ubuntu/entrypoint.sh /usr/local/bin/fta-entrypoint

RUN chmod +x /usr/local/bin/fta-entrypoint \
    && mkdir -p \
        data/face_images \
        data/faiss_index \
        data/models \
        data/snapshots

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/fta-entrypoint"]
