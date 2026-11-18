"""Start the local camera audio bridge once before launching FTA on Windows."""

import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]


def is_ready(api_url):
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(api_url.rstrip("/") + "/api", timeout=1) as response:
            info = json.load(response)
        return isinstance(info, dict) and all(
            key in info for key in ("version", "rtsp", "config_path")
        )
    except (OSError, ValueError):
        return False


def start(config=settings, root=ROOT):
    if not config.CAMERA_AUDIO_ENABLED:
        print("Camera audio disabled; skipping go2rtc.")
        return 0
    api_url = config.CAMERA_AUDIO_GO2RTC_URL
    if urlsplit(api_url).hostname not in ("127.0.0.1", "localhost", "::1"):
        print("Using remote go2rtc; local startup skipped.")
        return 0
    if is_ready(api_url):
        print("go2rtc is already running; reusing it.")
        return 0

    directory = root / "camera_test"
    executable = directory / "go2rtc.exe"
    yaml_path = directory / "go2rtc.yaml"
    if not executable.is_file() or not yaml_path.is_file():
        print("WARNING: camera_test/go2rtc.exe or go2rtc.yaml is missing.")
        return 1
    process = None
    ready = False
    try:
        with (directory / "go2rtc.stdout.log").open("ab") as output, (
            directory / "go2rtc.stderr.log"
        ).open("ab") as errors:
            process = subprocess.Popen(
                [str(executable), "-config", str(yaml_path)], cwd=str(directory),
                stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
            )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if is_ready(api_url):
                ready = True
                print("go2rtc started in the background; camera audio is ready.")
                return 0
            if process.poll() is not None:
                break
            time.sleep(0.25)
        print("WARNING: go2rtc API is not ready. Check camera_test/go2rtc.*.log and API port.")
    except OSError as exc:
        print(f"WARNING: cannot start go2rtc ({type(exc).__name__}).")
    finally:
        # Only stop our own failed startup, never an existing go2rtc instance.
        if process is not None and not ready and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    return 1


if __name__ == "__main__":
    raise SystemExit(start())
