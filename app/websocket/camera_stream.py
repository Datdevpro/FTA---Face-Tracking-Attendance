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

# Processing frame rate for recognition (lower = less CPU)
PROCESS_FPS = 5
FRAME_INTERVAL = 1.0 / PROCESS_FPS

# Max frame dimension for detection (resize larger frames)
MAX_DETECT_DIM = 480


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

    if not camera_service.is_running:
        camera_service.start()

    try:
        while True:
            start_time = time.time()

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

            # Run face detection and recognition in thread pool
            # to avoid blocking the async event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                _process_frame,
                frame,
                face_service,
                face_index,
                anti_spoofing,
                attendance_service,
            )

            annotated_frame = result["annotated_frame"]
            faces_data = result["faces"]
            attendance_events = result["attendance_events"]

            # Encode frame as JPEG base64
            _, buffer = cv2.imencode(
                ".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
            )
            frame_b64 = base64.b64encode(buffer).decode("utf-8")

            # Send frame and detection data
            message = {
                "type": "frame",
                "frame": frame_b64,
                "faces": faces_data,
                "attendance_events": attendance_events,
                "timestamp": datetime.now().isoformat(),
                "process_time_ms": round((time.time() - start_time) * 1000, 1),
            }
            await websocket.send_json(message)

            # Frame rate control
            elapsed = time.time() - start_time
            sleep_time = max(0, FRAME_INTERVAL - elapsed)
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
        camera_service.stop()


def _process_frame(
    frame: np.ndarray,
    face_service,
    face_index,
    anti_spoofing,
    attendance_service,
) -> dict:
    """
    Process a single frame: detect faces, recognize, check attendance.
    Runs in a thread pool executor.
    """
    annotated = frame.copy()
    faces_data = []
    attendance_events = []

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
            color = (0, 0, 255)  # Red for unknown

            # Anti-spoofing check
            if settings.ANTI_SPOOFING_ENABLED:
                is_live, liveness_score = anti_spoofing.check_liveness(
                    frame, bbox
                )
                if not is_live:
                    name = "SPOOF DETECTED"
                    color = (0, 0, 255)
                    faces_data.append({
                        "name": name,
                        "bbox": [x1, y1, x2, y2],
                        "is_live": False,
                        "liveness_score": round(liveness_score, 3),
                    })
                    # Draw red bbox for spoof
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        annotated, name, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
                    )
                    continue

            # Search in FAISS index
            matches = face_index.search(
                face.embedding,
                threshold=settings.FACE_RECOGNITION_THRESHOLD,
            )

            if matches:
                employee_id, similarity = matches[0]
                color = (0, 255, 0)  # Green for recognized
                name = _get_employee_name(employee_id)

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

            # Draw bounding box and name
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Label background
            label = f"{name} ({similarity:.0%})" if employee_id else name
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

            faces_data.append({
                "name": name,
                "employee_id": employee_id,
                "similarity": round(similarity, 4),
                "bbox": [x1, y1, x2, y2],
                "det_score": round(face.det_score, 3),
                "is_live": is_live,
            })

    except Exception as e:
        logger.error(f"Frame processing error: {e}")

    # Draw timestamp
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(
        annotated, ts, (10, annotated.shape[0] - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
    )

    return {
        "annotated_frame": annotated,
        "faces": faces_data,
        "attendance_events": attendance_events,
    }


def _get_employee_name(employee_id: int) -> str:
    cached_name = _employee_name_cache.get(employee_id)
    if cached_name:
        return cached_name

    db: Session = SessionLocal()
    try:
        from app.models.employee import Employee

        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if employee:
            _employee_name_cache[employee_id] = employee.full_name
            return employee.full_name
    finally:
        db.close()

    return "Unknown"
