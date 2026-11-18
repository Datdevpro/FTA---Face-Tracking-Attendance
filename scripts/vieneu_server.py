"""Loopback-only VieNeu v3 Turbo worker, run by .venv-vieneu Python."""

import argparse
import io
import json
import logging
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
logger = logging.getLogger("fta.vieneu")


class SpeechEngine:
    def __init__(self, args):
        self.args = args
        self.model = None
        self.error = None
        self.lock = threading.Lock()

    def load(self):
        try:
            from vieneu import Vieneu
            self.model = Vieneu(mode="v3turbo", backbone_repo=MODEL,
                                backend="onnx", device="cpu", precision="fp32",
                                threads=self.args.threads)
            # Warm up once before exposing ready=true.
            self.model.infer("Xin chào.", voice=self.args.voice)
            self.ready = True
            logger.info("VieNeu v3 Turbo ready; CPU threads=%s", self.args.threads)
        except Exception as exc:
            self.error = type(exc).__name__
            logger.exception("VieNeu model initialization failed")

    ready = False

    def synthesize(self, text, voice):
        import soundfile as sf
        audio = self.model.infer(text, voice=voice)
        if not 0 < len(audio) / self.model.sample_rate <= 60:
            raise ValueError("Invalid speech duration")
        wav = io.BytesIO()
        sf.write(wav, audio, self.model.sample_rate, format="WAV", subtype="PCM_16")
        result = subprocess.run(
            [self.args.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-vn", "-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1"],
            input=wav.getvalue(), capture_output=True, check=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout


def handler_for(engine):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass  # Do not log request bodies or employee names.

        def reply(self, code, data, content_type="application/json"):
            if isinstance(data, dict):
                data = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/voices":
                if not engine.ready:
                    return self.reply(503, {"error": "Model not ready"})
                return self.reply(200, {"voices": [{"label": label, "name": name}
                                                  for label, name in engine.model.list_preset_voices()]})
            if self.path != "/health":
                return self.reply(404, {"error": "Not found"})
            self.reply(200, {"service": "fta-vieneu", "model": MODEL,
                             "ready": engine.ready, "error": engine.error})

        def do_POST(self):
            if self.path != "/speech":
                return self.reply(404, {"error": "Not found"})
            if not engine.ready:
                return self.reply(503, {"error": "Model not ready"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    return self.reply(413, {"error": "Invalid request length"})
                body = json.loads(self.rfile.read(length))
                text = body.get("text")
                voice = body.get("voice") or engine.args.voice
                if not isinstance(text, str) or not 0 < len(text.strip()) <= 300 or not isinstance(voice, str):
                    return self.reply(400, {"error": "Invalid text or voice"})
            except (ValueError, AttributeError):
                return self.reply(400, {"error": "Invalid JSON"})
            if not engine.lock.acquire(blocking=False):
                return self.reply(429, {"error": "Speech worker busy"})
            try:
                self.reply(200, engine.synthesize(text.strip(), voice), "audio/mpeg")
            except Exception as exc:
                logger.error("Speech generation failed (%s)", type(exc).__name__)
                self.reply(500, {"error": "Speech generation failed"})
            finally:
                engine.lock.release()

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=1985)
    parser.add_argument("--voice", default="Mai Anh")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("HF_HOME", str(root / "data/models/vieneu-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
    engine = SpeechEngine(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(engine))
    threading.Thread(target=engine.load, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
