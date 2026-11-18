import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from app.api import tts
from scripts import start_vieneu, vieneu_server


@pytest.mark.asyncio
async def test_vieneu_runs_off_event_loop_without_calling_edge(monkeypatch):
    monkeypatch.setattr(tts.settings, "TTS_PROVIDER", "vieneu")
    loop_thread = threading.get_ident()

    def synthesize(text):
        assert text == "Hello"
        assert threading.get_ident() != loop_thread
        return b"MP3"

    monkeypatch.setattr(tts, "_synthesize_with_vieneu", synthesize)
    edge = AsyncMock()
    monkeypatch.setattr(tts, "_synthesize_with_edge_tts", edge)
    assert await tts.synthesize_welcome_audio(tts.TTSRequest(text="Hello")) == b"MP3"
    edge.assert_not_awaited()


@pytest.mark.asyncio
async def test_vieneu_failure_preserves_edge_and_gtts_fallbacks(monkeypatch):
    monkeypatch.setattr(tts.settings, "TTS_PROVIDER", "vieneu")
    monkeypatch.setattr(tts, "_synthesize_with_vieneu", Mock(side_effect=ConnectionError()))
    edge = AsyncMock(return_value=b"EDGE")
    monkeypatch.setattr(tts, "_synthesize_with_edge_tts", edge)
    gtts = Mock(return_value=b"GOOGLE")
    monkeypatch.setattr(tts, "_synthesize_with_gtts", gtts)
    request = tts.TTSRequest(text="Hello")
    assert await tts.synthesize_welcome_audio(request) == b"EDGE"
    gtts.assert_not_called()
    edge.side_effect = RuntimeError()
    assert await tts.synthesize_welcome_audio(request) == b"GOOGLE"


@pytest.mark.asyncio
async def test_edge_setting_skips_vieneu(monkeypatch):
    monkeypatch.setattr(tts.settings, "TTS_PROVIDER", "edge")
    local = Mock()
    monkeypatch.setattr(tts, "_synthesize_with_vieneu", local)
    monkeypatch.setattr(tts, "_synthesize_with_edge_tts", AsyncMock(return_value=b"EDGE"))
    assert await tts.synthesize_welcome_audio(tts.TTSRequest(text="Hello")) == b"EDGE"
    local.assert_not_called()


def test_worker_rejects_requests_until_ready_and_serializes_inference():
    import json
    engine = vieneu_server.SpeechEngine(SimpleNamespace(voice="test"))
    engine.synthesize = Mock(return_value=b"ID3-test")
    server = vieneu_server.ThreadingHTTPServer(("127.0.0.1", 0), vieneu_server.handler_for(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def speech(body):
        return urlopen(Request(base + "/speech", data=json.dumps(body).encode(), method="POST"), timeout=2)

    try:
        assert start_vieneu.status(base)["ready"] is False
        with pytest.raises(HTTPError) as error:
            speech({"text": "Hello"})
        assert error.value.code == 503
        engine.ready = True
        with pytest.raises(HTTPError) as error:
            speech({"text": " "})
        assert error.value.code == 400
        with engine.lock:
            with pytest.raises(HTTPError) as error:
                speech({"text": "Hello"})
            assert error.value.code == 429
        with speech({"text": "Hello"}) as response:
            assert response.headers.get_content_type() == "audio/mpeg"
            assert response.read() == b"ID3-test"
        engine.synthesize.assert_called_once_with("Hello", "test")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_start_vieneu_reuses_worker_and_respects_edge_setting(monkeypatch):
    config = SimpleNamespace(TTS_PROVIDER="vieneu", VIENEU_URL="http://127.0.0.1:1985")
    monkeypatch.setattr(start_vieneu, "status", Mock(return_value={"ready": True}))
    spawn = Mock()
    monkeypatch.setattr(start_vieneu.subprocess, "Popen", spawn)
    assert start_vieneu.start(config) == 0
    monkeypatch.setattr(start_vieneu, "status", Mock(return_value={"ready": False, "error": "RuntimeError"}))
    assert start_vieneu.start(config) == 1
    config.TTS_PROVIDER = "edge"
    assert start_vieneu.start(config) == 0
    spawn.assert_not_called()
