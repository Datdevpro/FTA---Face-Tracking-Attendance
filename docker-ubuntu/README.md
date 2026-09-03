# Deploy FTA on Jetson Nano with Docker

## Supported target

This package targets the original NVIDIA Jetson Nano running JetPack 4.6.x
(ARM64). NVIDIA lists JetPack 4.6.6 / L4T 32.7.6 as the final JetPack 4 release
supporting Jetson Nano:

- <https://developer.nvidia.com/embedded/jetpack-archive>
- <https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-4-with-the-release-of-jetpack-4-6-6/314300>

The Docker image uses Python 3.10 on Debian Bullseye ARM64. It does not depend
on the host's Ubuntu 18.04 Python 3.6 installation.

## Important GPU limitation

The provided Jetson image runs InsightFace and anti-spoofing through
`CPUExecutionProvider`. Do not change the provider values to `cuda` in this
image.

Jetson Nano JetPack 4.x uses CUDA 10.2. The desktop dependency
`onnxruntime-gpu==1.22.0` is not a compatible Jetson ARM64 GPU runtime.
Microsoft's Jetson documentation requires building a JetPack-matched ONNX
Runtime wheel separately and then installing that wheel into the application
image:

- <https://github.com/microsoft/onnxruntime/blob/main/dockerfiles/README.md#nvidia-jetson-tx1tx2nanoxavier>

GPU support therefore needs a separate, tested image or a TensorRT conversion
of the InsightFace and anti-spoofing models. The current package prioritizes a
repeatable image that can actually build and run on Nano.

## Prerequisites on the Jetson

1. Flash JetPack 4.6.x and boot the Jetson.
2. Connect the Jetson to the Internet.
3. Connect a USB webcam, or configure an RTSP URL later.
4. Install Docker and Compose:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
```

Optional: allow the current user to run Docker without `sudo`:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

## Build and start

Clone the repository directly on the Jetson Nano:

```bash
git clone https://github.com/Datdevpro/FTA---Face-Tracking-Attendance.git FTA
cd FTA
chmod +x docker-ubuntu/deploy.sh
./docker-ubuntu/deploy.sh
```

Build on the Jetson itself. The image is `linux/arm64`; building it on a normal
x86 PC requires ARM emulation and is much slower and less reliable.

The first build compiles InsightFace for ARM64 and can take a long time. The
first application startup downloads the `buffalo_l` model into the persistent
`data/models` directory.

## Open the application

Find the Jetson IP:

```bash
hostname -I
```

From another computer on the same network, open:

```text
http://JETSON_IP:8000
```

Default login:

```text
admin / admin123
```

Change this password before using real data.

## Camera configuration

The default Compose configuration passes `/dev/video0` into the container.
Check available cameras:

```bash
v4l2-ctl --list-devices
ls -l /dev/video*
```

For a different USB device:

```bash
FTA_CAMERA_DEVICE=/dev/video1 ./docker-ubuntu/deploy.sh
```

Then set `CAMERA_SOURCE=0` in `docker-ubuntu/.env`; the mapped device appears as
`/dev/video0` inside the container.

For RTSP, set `CAMERA_SOURCE` to the RTSP URL in `docker-ubuntu/.env` and remove
the `devices` section from `docker-ubuntu/docker-compose.yml` if no USB device
is needed.
The deployment script also maps `/dev/null` as a harmless placeholder when the
configured USB device does not exist, allowing the container to start.

## Persistent data

Compose bind-mounts the repository's `data/` directory to `/app/data`. This
persists:

- SQLite database and WAL files
- face images and attendance snapshots
- FAISS index
- downloaded InsightFace models
- pending checkout state

Back up this directory regularly:

```bash
tar -czf fta-data-backup.tar.gz data/
```

Stop the container before restoring a backup.

## Operations

```bash
# Status
docker-compose -f docker-ubuntu/docker-compose.yml ps

# Logs
docker-compose -f docker-ubuntu/docker-compose.yml logs -f fta

# Restart
docker-compose -f docker-ubuntu/docker-compose.yml restart fta

# Stop and remove the container (persistent data remains)
docker-compose -f docker-ubuntu/docker-compose.yml down

# Rebuild after a source update
git pull
docker-compose -f docker-ubuntu/docker-compose.yml up -d --build
```

## Performance settings

The defaults in `docker-ubuntu/.env` reduce load relative to desktop:

```env
CAMERA_FPS=15
STREAM_PREVIEW_FPS=10
RECOGNITION_INTERVAL_FRAMES=8
ANTI_SPOOFING_INTERVAL_FRAMES=10
```

If memory pressure is high, enable swap on the Jetson before building. Avoid
running multiple Uvicorn workers: each worker would load another copy of the
models and create independent camera access.
