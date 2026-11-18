import asyncio
import io
import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from app.api import tts
from app.config import Settings
from app.services import camera_audio
from app.services.camera_audio import CameraAudioService


def make_service(tmp_path, **overrides):
    return CameraAudioService(Settings(
        _env_file=None, CAMERA_AUDIO_DIR=str(tmp_path), **overrides,
    ))


@pytest.mark.asyncio
async def test_greetings_are_serialized_and_pending_employee_is_not_repeated(tmp_path):
    service = make_service(tmp_path, CAMERA_AUDIO_QUEUE_SIZE=1)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    played = []

    async def play(text):
        played.append(text)
        if text == "First":
            first_started.set()
            await release_first.wait()

    service._play = play
    service.start()
    try:
        assert service.enqueue({"employee_id": 1, "message": "First"})
        await asyncio.wait_for(first_started.wait(), 1)
        assert not service.enqueue({"employee_id": 1, "message": "First again"})
        assert service.enqueue({"employee_id": 2, "message": "Second"})
        assert not service.enqueue({"employee_id": 3, "message": "Queue full"})
        assert played == ["First"]
        release_first.set()
        await asyncio.wait_for(service._queue.join(), 1)
        assert played == ["First", "Second"]
        assert not service._pending
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_playback_failure_does_not_stop_later_greetings(tmp_path):
    service = make_service(tmp_path)
    service._play = AsyncMock(side_effect=[ConnectionError(), None])
    service.start()
    try:
        assert service.enqueue({"employee_id": 1, "message": "First"})
        assert service.enqueue({"employee_id": 2, "message": "Second"})
        await asyncio.wait_for(service._queue.join(), 1)
        assert service._play.await_count == 2
        assert not service._pending
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_disabled_audio_does_not_create_worker_or_accept_events(tmp_path):
    service = make_service(tmp_path, CAMERA_AUDIO_ENABLED=False)
    service.start()
    assert not service.enqueue({"message": "Hello"})
    assert service._worker is None
    await service.close()


@pytest.mark.asyncio
async def test_playback_waits_for_audio_and_stops_before_cleaning_up(tmp_path, monkeypatch):
    service = make_service(tmp_path, CAMERA_AUDIO_GO2RTC_DIR="/shared/audio")
    service._ensure_backchannel = lambda: None
    monkeypatch.setattr(camera_audio, "synthesize_welcome_audio", AsyncMock(return_value=b"MP3"))
    calls = []

    def prepare(mp3, wav):
        assert mp3.read_bytes() == b"MP3"
        wav.write_bytes(b"WAV")
        return 3.0

    def post(source):
        assert list(tmp_path.glob("*.wav"))  # Keep files until playback has stopped.
        calls.append(source)

    async def sleep(duration):
        assert duration >= 3.0
        assert len(calls) == 1  # No next greeting or early stop.

    service._prepare_wav = prepare
    service._post = post
    monkeypatch.setattr(camera_audio.asyncio, "sleep", sleep)
    await service._play("Xin chào")
    assert calls[0].startswith("ffmpeg:/shared/audio/")
    assert calls[0].endswith(".wav#audio=pcma/8000#input=file")
    assert calls[1] == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_shutdown_stops_active_camera_and_removes_audio(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    service._ensure_backchannel = lambda: None
    monkeypatch.setattr(camera_audio, "synthesize_welcome_audio", AsyncMock(return_value=b"MP3"))
    started = asyncio.Event()
    loop = asyncio.get_running_loop()
    calls = []

    def prepare(mp3, wav):
        wav.write_bytes(b"WAV")
        return 30.0

    def post(source):
        calls.append(source)
        if source:
            loop.call_soon_threadsafe(started.set)

    service._prepare_wav = prepare
    service._post = post
    service.start()
    service.enqueue({"employee_id": 1, "message": "Hello"})
    await asyncio.wait_for(started.wait(), 1)
    await service.close()
    assert calls[-1] == ""
    assert list(tmp_path.iterdir()) == []
    assert not service._pending


@pytest.mark.asyncio
async def test_cleanup_retries_when_ffmpeg_still_has_wav_open(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    path = tmp_path / "welcome.wav"
    path.write_bytes(b"WAV")
    unlink = Path.unlink
    attempts = []

    def locked_once(self, **kwargs):
        attempts.append(self)
        if len(attempts) == 1:
            raise PermissionError("FFmpeg still owns this file")
        return unlink(self, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_once)
    monkeypatch.setattr(camera_audio.asyncio, "sleep", AsyncMock())
    await service._remove_audio_files(path)
    assert len(attempts) == 2
    assert not path.exists()


@pytest.mark.asyncio
async def test_missing_backchannel_does_not_synthesize_or_spawn_ffmpeg(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    synthesis = AsyncMock()
    monkeypatch.setattr(camera_audio, "synthesize_welcome_audio", synthesis)

    def unavailable():
        raise RuntimeError("No backchannel")

    service._ensure_backchannel = unavailable
    with pytest.raises(RuntimeError, match="No backchannel"):
        await service._play("Xin chào")
    synthesis.assert_not_awaited()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("medias,available", [
    (["audio, recvonly, MPEG4-GENERIC/16000"], False),
    (["audio, sendonly, PCMU/8000"], False),
    (["audio, recvonly, MPEG4-GENERIC/16000", "audio, sendonly, PCMA/8000"], True),
])
def test_probe_requires_a_camera_output_with_the_supported_codec(tmp_path, monkeypatch,
                                                               medias, available):
    service = make_service(tmp_path)

    class Opener:
        def open(self, url, timeout):
            assert parse_qs(urlsplit(url).query)["src"] == ["imou"]
            return io.BytesIO(json.dumps({"producers": [{"medias": medias}]}).encode())

    monkeypatch.setattr(camera_audio, "build_opener", lambda handler: Opener())
    if available:
        service._ensure_backchannel()
    else:
        with pytest.raises(RuntimeError, match="backchannel"):
            service._ensure_backchannel()


def test_go2rtc_request_encodes_file_path_and_disables_inherited_proxies(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    source = "ffmpeg:D:/audio folder/welcome.wav#audio=pcma/8000#input=file"
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"{}"

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response()

    def build(handler):
        assert handler.proxies == {}
        return Opener()

    monkeypatch.setattr(camera_audio, "build_opener", build)
    service._post(source)
    request = requests[0]
    url = urlsplit(request.full_url)
    assert request.method == "POST"
    assert not url.fragment
    assert parse_qs(url.query) == {"dst": ["imou"], "src": [source]}


@pytest.mark.asyncio
async def test_tts_fallback_runs_off_the_event_loop(monkeypatch):
    monkeypatch.setattr(tts.settings, "TTS_PROVIDER", "edge")
    loop_thread = threading.get_ident()
    monkeypatch.setattr(tts, "_synthesize_with_edge_tts", AsyncMock(side_effect=RuntimeError()))

    def fallback(text):
        assert threading.get_ident() != loop_thread
        assert text == "Xin chào"
        return b"MP3"

    monkeypatch.setattr(tts, "_synthesize_with_gtts", fallback)
    assert await tts.synthesize_welcome_audio(tts.TTSRequest(text="Xin chào")) == b"MP3"
