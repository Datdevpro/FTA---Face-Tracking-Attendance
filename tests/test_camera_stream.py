import cv2
import numpy as np
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock
from fastapi import WebSocketDisconnect
from app.config import Settings, settings
from app.websocket import camera_stream

from app.websocket.camera_stream import (
    MAX_BROWSER_FRAME_BYTES,
    _decode_browser_frame,
)
from app.services.camera_service import CameraService


def test_decode_browser_frame_accepts_jpeg():
    source = np.zeros((24, 32, 3), dtype=np.uint8)
    source[:, :, 1] = 180
    encoded, buffer = cv2.imencode(".jpg", source)

    assert encoded is True
    decoded = _decode_browser_frame(buffer.tobytes())
    assert decoded is not None
    assert decoded.shape == source.shape


def test_decode_browser_frame_rejects_invalid_and_oversized_payloads():
    assert _decode_browser_frame(b"") is None
    assert _decode_browser_frame(b"not-a-jpeg") is None
    assert _decode_browser_frame(b"0" * (MAX_BROWSER_FRAME_BYTES + 1)) is None


def test_browser_stream_updates_camera_status_without_opening_device():
    service = CameraService(source="browser")
    service.start()
    assert service.is_running is False

    service.set_external_stream_active(True)
    assert service.get_status()["connected"] is True
    assert service.get_status()["mode"] == "browser"

    service.set_external_stream_active(False)
    assert service.is_connected is False


def test_rtsp_reconnect_releases_old_capture_and_clears_stale_frame(monkeypatch):
    service = CameraService(
        source="rtsp://example.test/stream", rtsp_open_timeout_ms=1200,
        rtsp_read_timeout_ms=2400,
    )
    old_capture = Mock()
    service._cap = old_capture
    service._frame = np.zeros((2, 2, 3), dtype=np.uint8)
    capture = Mock()
    capture.isOpened.return_value = True
    open_capture = Mock(return_value=capture)
    monkeypatch.setattr(cv2, "VideoCapture", open_capture)

    service._connect()

    old_capture.release.assert_called_once()
    assert service.get_frame() is None
    assert service.is_connected is True
    open_capture.assert_called_once_with(
        service.source, cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1200,
         cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2400],
    )
    capture.set.assert_not_called()  # RTSP resolution/FPS belong to the camera.


def test_failed_rtsp_connection_remains_disconnected(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    service = CameraService(source="rtsp://example.test/offline")
    service._connect()
    assert service.is_connected is False


def test_rtsp_capture_does_not_sleep_between_frames(monkeypatch):
    service = CameraService(source="rtsp://example.test/stream")
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    capture = Mock()
    capture.isOpened.return_value = True

    def read_one_frame():
        service._running = False
        return True, frame

    capture.read.side_effect = read_one_frame
    service._cap = capture
    service._connected = True
    service._running = True
    sleep = Mock()
    monkeypatch.setattr("app.services.camera_service.time.sleep", sleep)
    service._capture_loop()
    sleep.assert_not_called()
    np.testing.assert_array_equal(service.get_frame(), frame)


def test_usb_camera_keeps_device_settings(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    service = CameraService(source=0, width=800, height=600, fps=15)
    service._connect()
    capture.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 800)
    capture.set.assert_any_call(cv2.CAP_PROP_FRAME_HEIGHT, 600)
    capture.set.assert_any_call(cv2.CAP_PROP_FPS, 15)
    assert service.is_connected is True


@pytest.mark.parametrize("camera_id,expected", [
    ("webcam", 0),
    ("imou_rotate", "rtsp://example.test/rotate"),
    ("imou_fixed", "rtsp://example.test/fixed"),
    (None, "browser"),
])
def test_named_camera_sources_are_independent_of_legacy_source(camera_id, expected):
    config = Settings(
        _env_file=None, CAMERA_SOURCE="browser",
        CAMERA_IMOU_ROTATE_RTSP="rtsp://example.test/rotate",
        CAMERA_IMOU_FIXED_RTSP="rtsp://example.test/fixed",
    )
    assert config.camera_source_for(camera_id) == expected


@pytest.mark.parametrize("camera_id,url,expected", [
    ("imou_rotate", "", "CAMERA_IMOU_ROTATE_RTSP"),
    ("imou_fixed", "", "CAMERA_IMOU_FIXED_RTSP"),
    ("imou_rotate", "http://example.test", "URL RTSP"),
    ("rtsp://client-supplied.test", "", "không hợp lệ"),
])
def test_invalid_camera_choices_give_actionable_errors(camera_id, url, expected):
    config = Settings(_env_file=None, CAMERA_IMOU_ROTATE_RTSP=url,
                      CAMERA_IMOU_FIXED_RTSP="")
    with pytest.raises(ValueError, match=expected):
        config.camera_source_for(camera_id)


@pytest.mark.parametrize("camera_id,expected", [
    ("webcam", 0), ("imou_fixed", "rtsp://example.test/fixed"),
])
def test_websocket_uses_selected_source_and_releases_camera(monkeypatch, camera_id, expected):
    monkeypatch.setattr(settings, "CAMERA_IMOU_FIXED_RTSP", "rtsp://example.test/fixed")
    websocket = Mock(query_params={"camera": camera_id})
    websocket.accept = AsyncMock()
    websocket.send_json = AsyncMock(side_effect=[None, WebSocketDisconnect()])
    service = Mock(source="rtsp://example.test/old", is_running=False)
    service.get_frame.return_value = None
    service.get_status.return_value = {}

    asyncio.run(camera_stream.camera_stream_handler(
        websocket, None, None, None, None, service,
    ))

    assert service.source == expected
    service.start.assert_called_once()
    assert service.stop.call_count == 2  # Before switching and on disconnect.
    assert websocket.send_json.call_args_list[0].args[0]["mode"] == "backend"
    assert not camera_stream._camera_stream_lock.locked()


def test_unconfigured_camera_does_not_stop_or_change_current_camera(monkeypatch):
    monkeypatch.setattr(settings, "CAMERA_IMOU_FIXED_RTSP", "")
    websocket = Mock(query_params={"camera": "imou_fixed"})
    websocket.accept = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()
    service = Mock(source=0)
    asyncio.run(camera_stream.camera_stream_handler(websocket, None, None, None, None, service))
    service.stop.assert_not_called()
    service.start.assert_not_called()
    assert service.source == 0
    assert "CAMERA_IMOU_FIXED_RTSP" in websocket.send_json.call_args.args[0]["message"]
    websocket.close.assert_awaited_once_with(code=1008)


def test_second_viewer_cannot_switch_or_stop_active_camera():
    async def check():
        websocket = Mock(query_params={"camera": "webcam"})
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        websocket.close = AsyncMock()
        service = Mock(source="rtsp://example.test/active")
        async with camera_stream._camera_stream_lock:
            await camera_stream.camera_stream_handler(websocket, None, None, None, None, service)
            service.start.assert_not_called()
            service.stop.assert_not_called()
            websocket.close.assert_awaited_once_with(code=1013)
    asyncio.run(check())
