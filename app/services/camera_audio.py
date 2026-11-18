"""Queue welcome speech and send it to a camera through go2rtc."""

import asyncio
import json
import logging
import subprocess
import time
import uuid
import wave
from contextlib import suppress
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from app.api.tts import TTSRequest, synthesize_welcome_audio

logger = logging.getLogger(__name__)


class CameraAudioService:
    """One worker owns playback so go2rtc never replaces an ongoing greeting."""

    def __init__(self, config):
        self.config = config
        self._queue = asyncio.Queue(maxsize=config.CAMERA_AUDIO_QUEUE_SIZE)
        self._pending = set()
        self._worker = None

    def start(self):
        if self.config.CAMERA_AUDIO_ENABLED and self._worker is None:
            self._worker = asyncio.create_task(self._run())
            logger.info("Camera welcome audio enabled; stream=%s", self.config.CAMERA_AUDIO_STREAM)

    async def close(self):
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        self._pending.clear()

    def enqueue(self, event: dict) -> bool:
        """Accept recognition events without waiting for TTS or network I/O."""
        if not self.config.CAMERA_AUDIO_ENABLED or self._worker is None:
            return False
        text = " ".join(str(event.get("message") or "").split()).replace(",", ".")
        if not text or len(text) > 300:
            return False
        key = event.get("employee_id") or event.get("employee_code") or text
        if key in self._pending:
            return False
        try:
            self._queue.put_nowait((key, text, time.monotonic(), event.get("greeting_managed", False)))
        except asyncio.QueueFull:
            logger.warning("Camera welcome queue is full; skipping greeting")
            return False
        self._pending.add(key)
        return True

    async def _run(self):
        while True:
            key, text, queued_at, managed = await self._queue.get()
            try:
                # Do not play stale greetings after a burst of arrivals.
                if time.monotonic() - queued_at < 30:
                    if managed:
                        from app.services.employee_greetings import current
                        greeting = await asyncio.to_thread(current, key)
                        if greeting and greeting["welcome_status"] == "ready":
                            await self._play(greeting["welcome_text"], greeting["welcome_audio_key"])
                    else:
                        await self._play(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Do not log go2rtc response bodies, which can contain camera URLs.
                logger.error(
                    "Camera welcome playback failed (%s): %s",
                    type(exc).__name__, exc,
                )
            finally:
                self._pending.discard(key)
                self._queue.task_done()

    async def _play(self, text: str, cached_key: str | None = None):
        # Check the camera before spawning an FFmpeg source in go2rtc. A failed
        # codec match in go2rtc 1.9.15 can leave that source running indefinitely.
        await self._finish_thread(self._ensure_backchannel)
        if cached_key:
            from app.services.employee_greetings import audio_path
            cached_wav = audio_path(cached_key)
            with wave.open(str(cached_wav), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            await self._send_wav(cached_wav, duration)
            return
        audio = await asyncio.wait_for(
            synthesize_welcome_audio(TTSRequest(text=text)), timeout=40
        )
        directory = Path(self.config.CAMERA_AUDIO_DIR).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        identifier = uuid.uuid4().hex
        mp3_path = directory / f"{identifier}.mp3"
        wav_path = directory / f"{identifier}.wav"
        try:
            mp3_path.write_bytes(audio)
            # Decode once to PCM WAV so its exact duration is available via wave.
            # Waiting for that duration prevents the next POST cutting speech off.
            duration = await self._finish_thread(self._prepare_wav, mp3_path, wav_path)
            await self._send_wav(wav_path, duration)
        finally:
            await self._remove_audio_files(mp3_path, wav_path)

    async def _send_wav(self, wav_path, duration):
        remote_directory = self.config.CAMERA_AUDIO_GO2RTC_DIR
        if wav_path.parent == Path(self.config.EMPLOYEE_GREETING_DIR).resolve():
            remote_directory = self.config.EMPLOYEE_GREETING_GO2RTC_DIR
        source_path = str(PurePosixPath(remote_directory) / wav_path.name) if remote_directory else wav_path.as_posix()
        try:
            await self._finish_thread(self._post, f"ffmpeg:{source_path}#audio=pcma/8000#input=file")
            logger.info("Playing camera welcome; stream=%s, duration=%.1fs", self.config.CAMERA_AUDIO_STREAM, duration)
            await asyncio.sleep(duration + 1.5)
            logger.info("Camera welcome playback completed; stream=%s", self.config.CAMERA_AUDIO_STREAM)
        finally:
            try:
                await self._finish_thread(self._post, "")
            except Exception as exc:
                logger.warning("Unable to stop camera audio (%s)", type(exc).__name__)

    async def _remove_audio_files(self, *paths):
        pending = list(paths)
        # Windows can keep the WAV open briefly while FFmpeg exits.
        for attempt in range(15):
            remaining = []
            for path in pending:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    remaining.append(path)
            if not remaining:
                return
            pending = remaining
            if attempt < 14:
                await asyncio.sleep(0.2)
        logger.warning("Unable to remove %s temporary camera audio files", len(pending))

    @staticmethod
    async def _finish_thread(function, *args):
        # Let file/network operations finish before cancellation cleans up files.
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with suppress(Exception):
                await task
            raise

    def _prepare_wav(self, mp3_path: Path, wav_path: Path) -> float:
        subprocess.run(
            [self.config.CAMERA_AUDIO_FFMPEG_BIN, "-nostdin", "-hide_banner",
             "-loglevel", "error", "-y", "-i", str(mp3_path),
             "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(wav_path)],
            check=True, capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with wave.open(str(wav_path), "rb") as decoded:
            duration = decoded.getnframes() / decoded.getframerate()
        if not 0 < duration <= 60:
            raise ValueError("Welcome speech must be between 0 and 60 seconds")
        return duration

    def _post(self, source: str):
        query = urlencode({"dst": self.config.CAMERA_AUDIO_STREAM, "src": source})
        url = self.config.CAMERA_AUDIO_GO2RTC_URL.rstrip("/") + "/api/streams?" + query
        request = Request(url, data=b"", method="POST")
        # Local go2rtc traffic must not use inherited public HTTP proxies.
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(request, timeout=10) as response:
                response.read()
        except HTTPError as exc:
            raise RuntimeError(f"go2rtc HTTP {exc.code}") from None
        except URLError:
            raise ConnectionError("Cannot connect to go2rtc") from None

    def _ensure_backchannel(self):
        query = urlencode({"src": self.config.CAMERA_AUDIO_STREAM, "audio": ""})
        url = self.config.CAMERA_AUDIO_GO2RTC_URL.rstrip("/") + "/api/streams?" + query
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(url, timeout=10) as response:
                state = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"go2rtc probe HTTP {exc.code}") from None
        except URLError:
            raise ConnectionError("Cannot connect to go2rtc") from None
        for producer in state.get("producers", []):
            for media in producer.get("medias", []):
                if media.startswith("audio, sendonly,") and "PCMA/8000" in media:
                    return
        raise RuntimeError(
            "Camera has no PCMA/8000 backchannel; check proto=Onvif, "
            "close other talk sessions, then restart go2rtc"
        )
