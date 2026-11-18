"""Start an isolated VieNeu worker without delaying FTA model initialization."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]


def status(url):
    try:
        with build_opener(ProxyHandler({})).open(url.rstrip("/") + "/health", timeout=1) as response:
            info = json.load(response)
        return info if info.get("service") == "fta-vieneu" else None
    except (OSError, ValueError, AttributeError):
        return None


def start(config=settings, root=ROOT):
    if config.TTS_PROVIDER != "vieneu":
        return 0
    url = urlsplit(config.VIENEU_URL)
    if url.hostname not in ("127.0.0.1", "localhost"):
        print("Using external VieNeu worker.")
        return 0
    existing = status(config.VIENEU_URL)
    if existing:
        if existing.get("error"):
            print("VieNeu model failed to load; see data/logs/vieneu.stderr.log. Edge TTS remains available.")
            return 1
        print("VieNeu worker already running; " + ("ready." if existing.get("ready") else "loading model."))
        return 0
    python = root / ".venv-vieneu" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("VieNeu environment missing; run setup-vieneu.bat. Edge TTS remains available.")
        return 1
    logs = root / "data/logs"
    logs.mkdir(parents=True, exist_ok=True)
    ffmpeg = Path(config.CAMERA_AUDIO_FFMPEG_BIN)
    ffmpeg_arg = str((root / ffmpeg).resolve()) if ffmpeg.parent != Path(".") else str(ffmpeg)
    with (logs / "vieneu.stdout.log").open("ab") as output, (logs / "vieneu.stderr.log").open("ab") as errors:
        process = subprocess.Popen(
            [str(python), str(root / "scripts/vieneu_server.py"), "--port", str(url.port or 1985),
             "--voice", config.VIENEU_VOICE, "--threads", str(config.VIENEU_THREADS),
             "--ffmpeg", ffmpeg_arg],
            cwd=str(root), stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    for _ in range(12):
        if status(config.VIENEU_URL):
            print("VieNeu worker started; model warms up in the background. Edge TTS is the fallback.")
            return 0
        if process.poll() is not None:
            break
        time.sleep(0.25)
    print("VieNeu worker is not responding; see data/logs/vieneu.stderr.log. Edge TTS remains available.")
    return 1


if __name__ == "__main__":
    raise SystemExit(start())
