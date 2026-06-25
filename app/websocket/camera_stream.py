"""
WebSocket handler for real-time camera face recognition streaming.

Captures frames from camera, runs face detection + recognition,
annotates frames with bounding boxes and names, and streams
results back to the browser via WebSocket.
"""

import asyncio
import base64
import json
import logging
import time
from datetime import datetime

import cv2
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)
_employee_name_cache = {}
_employee_info_cache = {}
_liveness_cache = {}
_welcome_cache = {}
_stream_frame_counter = 0
_recognition_frame_counter = 0

# Max frame dimension for detection (resize larger frames)
MAX_DETECT_DIM = 480
WELCOME_REPEAT_SECONDS = 8


async def camera_stream_handler(
    websocket: WebSocket,
    face_service,
    face_index,
    anti_spoofing,
    attendance_service,
    camera_service,
):
    """
    WebSocket endpoint for live camera recognition stream.

    Sends JSON messages with:
    - Annotated frame as base64 JPEG
    - Detected faces with identities
    - Attendance events
    """
    await websocket.accept()
    logger.info("WebSocket client connected for camera stream")
    global _stream_frame_counter, _recognition_frame_counter

    if not camera_service.is_running:
        camera_service.start()

    loop = asyncio.get_event_loop()
    preview_interval = 1.0 / max(1, settings.STREAM_PREVIEW_FPS)
    recognition_interval = max(1, settings.RECOGNITION_INTERVAL_FRAMES)
    max_stale_seconds = max(0, settings.RECOGNITION_MAX_STALE_MS) / 1000

    recognition_future = None
    latest_faces = []
    latest_recognition_time_ms = None
    latest_recognition_at = 0.0

    try:
        while True:
            _stream_frame_counter += 1
            start_time = time.time()
            attendance_events = []
            recognition_ran = False

            # Get frame from camera
            frame = camera_service.get_frame()
            if frame is None:
                status = camera_service.get_status()
                message = "Camera is starting" if status.get("starting") else "Camera not available"
                await websocket.send_json({
                    "type": "status",
                    "message": message,
                    "status": status,
                })
                await asyncio.sleep(0.2)
                continue

            if recognition_future and recognition_future.done():
                try:
                    result = recognition_future.result()
                    latest_faces = result["faces"]
                    attendance_events = result["attendance_events"]
                    welcome_events = result["welcome_events"]
                    latest_recognition_time_ms = result["recognition_time_ms"]
                    latest_recognition_at = time.time()
                    recognition_ran = True
                except Exception as e:
                    logger.error(f"Recognition worker error: {e}")
                finally:
                    recognition_future = None

            should_run_recognition = (
                recognition_future is None
                and (
                    latest_recognition_at == 0
                    or _stream_frame_counter % recognition_interval == 0
                )
            )
            if should_run_recognition:
                _recognition_frame_counter += 1
                recognition_future = loop.run_in_executor(
                    None,
                    _run_recognition,
                    frame.copy(),
                    _recognition_frame_counter,
                    face_service,
                    face_index,
                    anti_spoofing,
                    attendance_service,
                )

            recognition_age = time.time() - latest_recognition_at if latest_recognition_at else None
            display_faces = latest_faces
            if recognition_age is not None and max_stale_seconds and recognition_age > max_stale_seconds:
                display_faces = []

            annotated_frame = _draw_overlay(frame, display_faces)

            # Encode frame as JPEG base64
            _, buffer = cv2.imencode(
                ".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
            )
            frame_b64 = base64.b64encode(buffer).decode("utf-8")

            # Send frame and detection data
            message = {
                "type": "frame",
                "frame": frame_b64,
                "faces": display_faces,
                "attendance_events": attendance_events,
                "welcome_events": welcome_events if recognition_ran else [],
                "timestamp": datetime.now().isoformat(),
                "process_time_ms": round((time.time() - start_time) * 1000, 1),
                "recognition_time_ms": latest_recognition_time_ms,
                "recognition_age_ms": round(recognition_age * 1000, 1) if recognition_age is not None else None,
                "recognition_pending": recognition_future is not None,
                "recognition_ran": recognition_ran,
            }
            await websocket.send_json(message)

            # Preview frame rate control
            elapsed = time.time() - start_time
            sleep_time = max(0, preview_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        _liveness_cache.clear()
        _welcome_cache.clear()
        camera_service.stop()


def _run_recognition(
    frame: np.ndarray,
    recognition_index: int,
    face_service,
    face_index,
    anti_spoofing,
    attendance_service,
) -> dict:
    """
    Run face detection, recognition, liveness, and attendance.
    Runs in a thread pool executor.
    """
    start_time = time.time()
    faces_data = []
    attendance_events = []
    welcome_events = []

    try:
        # Resize frame for faster detection if needed
        h, w = frame.shape[:2]
        scale = 1.0
        detect_frame = frame
        if max(h, w) > MAX_DETECT_DIM:
            scale = MAX_DETECT_DIM / max(h, w)
            detect_frame = cv2.resize(frame, None, fx=scale, fy=scale)

        # Detect faces on the (potentially smaller) frame
        faces = face_service.detect_faces(
            detect_frame, min_det_score=settings.FACE_DETECTION_THRESHOLD
        )

        for face in faces:
            # Scale bbox back to original frame size
            bbox = face.bbox / scale if scale != 1.0 else face.bbox
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])

            # Default: unknown face
            name = "Unknown"
            employee_id = None
            similarity = 0.0
            is_live = True
            liveness_score = None
            liveness_checked = False
            color = (0, 0, 255)  # Red for unknown

            # Search in FAISS index
            matches = face_index.search(
                face.embedding,
                threshold=settings.FACE_RECOGNITION_THRESHOLD,
            )

            if matches:
                employee_id, similarity = matches[0]
                color = (0, 255, 0)  # Green for recognized
                employee_info = _get_employee_info(employee_id)
                name = employee_info["name"]

                if settings.ANTI_SPOOFING_ENABLED:
                    is_live, liveness_score, liveness_checked = _get_liveness_result(
                        employee_id,
                        recognition_index,
                        frame,
                        bbox,
                        anti_spoofing,
                    )
                    if not is_live:
                        name = "SPOOF DETECTED"
                        color = (0, 0, 255)

                if is_live:
                    if _should_emit_welcome(employee_id):
                        welcome_events.append(
                            _build_welcome_event(employee_info, frame, bbox)
                        )

                    db: Session = SessionLocal()
                    try:
                        event = attendance_service.process_recognition(
                            db=db,
                            employee_id=employee_id,
                            confidence=similarity,
                        )
                        if event:
                            attendance_events.append(event)
                    finally:
                        db.close()

            faces_data.append({
                "name": name,
                "employee_id": employee_id,
                "similarity": round(similarity, 4),
                "bbox": [x1, y1, x2, y2],
                "det_score": round(face.det_score, 3),
                "is_live": is_live,
                "liveness_score": round(liveness_score, 3) if liveness_score is not None else None,
                "liveness_checked": liveness_checked,
            })

    except Exception as e:
        logger.error(f"Frame processing error: {e}")

    return {
        "faces": faces_data,
        "attendance_events": attendance_events,
        "welcome_events": welcome_events,
        "recognition_time_ms": round((time.time() - start_time) * 1000, 1),
    }


def _build_welcome_event(employee_info: dict, frame: np.ndarray, bbox: np.ndarray) -> dict:
    """Build a UI welcome payload with a cropped capture of the recognized face."""
    name = employee_info.get("name") or "bạn"
    message = f"Xin chào {name}. Chúc bạn một ngày tốt lành."
    captured_frame = _encode_face_capture(frame, bbox)

    return {
        "employee_id": employee_info.get("id"),
        "employee_code": employee_info.get("code"),
        "employee_name": name,
        "message": message,
        "image": captured_frame,
        "time": datetime.now().isoformat(),
    }


def _encode_face_capture(frame: np.ndarray, bbox: np.ndarray) -> str | None:
    """Encode a padded crop around the recognized face as base64 JPEG."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    face_w = max(1, x2 - x1)
    face_h = max(1, y2 - y1)
    pad_x = int(face_w * 0.35)
    pad_y = int(face_h * 0.45)

    crop_x1 = max(0, x1 - pad_x)
    crop_y1 = max(0, y1 - pad_y)
    crop_x2 = min(w, x2 + pad_x)
    crop_y2 = min(h, y2 + pad_y)

    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
    if crop.size == 0:
        crop = frame

    ok, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return None
    return base64.b64encode(buffer).decode("utf-8")


def _draw_overlay(frame: np.ndarray, faces_data: list[dict]) -> np.ndarray:
    """Draw the latest recognition result on a preview frame."""
    annotated = frame.copy()

    for face in faces_data:
        x1, y1, x2, y2 = [int(v) for v in face.get("bbox", [0, 0, 0, 0])]
        employee_id = face.get("employee_id")
        name = face.get("name") or "Unknown"
        similarity = float(face.get("similarity") or 0.0)
        is_live = face.get("is_live", True)

        if not is_live:
            color = (0, 0, 255)
        elif employee_id:
            color = (0, 255, 0)
        else:
            color = (0, 0, 255)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"{name} ({similarity:.0%})" if employee_id and is_live else name
        label_size, _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        )
        cv2.rectangle(
            annotated,
            (x1, y1 - label_size[1] - 10),
            (x1 + label_size[0], y1),
            color,
            -1,
        )
        cv2.putText(
            annotated, label, (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
        )

    # Draw timestamp
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(
        annotated, ts, (10, annotated.shape[0] - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
    )

    return annotated


def _get_employee_name(employee_id: int) -> str:
    return _get_employee_info(employee_id)["name"]


def _get_employee_info(employee_id: int) -> dict:
    cached_info = _employee_info_cache.get(employee_id)
    if cached_info:
        return cached_info

    cached_name = _employee_name_cache.get(employee_id)
    if cached_name:
        return {"id": employee_id, "code": None, "name": cached_name}

    db: Session = SessionLocal()
    try:
        from app.models.employee import Employee

        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if employee:
            info = {
                "id": employee.id,
                "code": employee.employee_code,
                "name": employee.full_name,
            }
            _employee_name_cache[employee_id] = employee.full_name
            _employee_info_cache[employee_id] = info
            return info
    finally:
        db.close()

    return {"id": employee_id, "code": None, "name": "Unknown"}


def _should_emit_welcome(employee_id: int) -> bool:
    now = time.time()
    last_emit = _welcome_cache.get(employee_id)
    if last_emit and now - last_emit < WELCOME_REPEAT_SECONDS:
        return False

    _welcome_cache[employee_id] = now
    return True


def _get_liveness_result(
    employee_id: int,
    frame_index: int,
    frame: np.ndarray,
    bbox: np.ndarray,
    anti_spoofing,
) -> tuple[bool, float, bool]:
    interval = max(1, settings.ANTI_SPOOFING_INTERVAL_FRAMES)
    cached = _liveness_cache.get(employee_id)

    if cached and frame_index % interval != 0:
        return cached["is_live"], cached["score"], False

    is_live, score = anti_spoofing.check_liveness(frame, bbox)
    _liveness_cache[employee_id] = {
        "is_live": is_live,
        "score": score,
        "frame_index": frame_index,
        "checked_at": time.time(),
    }
    return is_live, score, True
