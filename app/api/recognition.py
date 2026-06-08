"""
Face recognition API endpoints.
Handles face registration, verification, and management.
"""

import logging
import uuid
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recognition", tags=["Face Recognition"])


def _get_face_service():
    """Get the global face recognition service instance."""
    from app.main import face_service
    return face_service


def _get_face_index():
    """Get the global FAISS index instance."""
    from app.main import face_index
    return face_index


@router.post("/register/{employee_id}")
async def register_face(
    employee_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Register face(s) for an employee by uploading image files.

    Upload 1-5 images of the employee's face from different angles.
    The system will detect the face, assess quality, and store the embedding.
    """
    # Validate employee exists
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    if len(files) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 images allowed per registration",
        )

    face_service = _get_face_service()
    face_index_mgr = _get_face_index()
    images_dir = Path(settings.FACE_IMAGES_DIR) / str(employee_id)
    images_dir.mkdir(parents=True, exist_ok=True)

    registered = []
    errors = []

    for i, file in enumerate(files):
        try:
            # Read and decode image
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                errors.append(f"File {file.filename}: Invalid image format")
                continue

            # Detect faces
            faces = face_service.detect_faces(
                frame, min_det_score=settings.FACE_DETECTION_THRESHOLD
            )

            if len(faces) == 0:
                errors.append(f"File {file.filename}: No face detected")
                continue

            if len(faces) > 1:
                errors.append(
                    f"File {file.filename}: Multiple faces detected, "
                    f"please use a single-person photo"
                )
                continue

            face = faces[0]

            # Check quality
            if face.quality_score < settings.FACE_MIN_QUALITY:
                errors.append(
                    f"File {file.filename}: Face quality too low "
                    f"({face.quality_score:.2f} < {settings.FACE_MIN_QUALITY})"
                )
                continue

            # Save image to disk
            image_filename = f"{uuid.uuid4().hex}.jpg"
            image_path = images_dir / image_filename
            cv2.imwrite(str(image_path), frame)

            # Save embedding to database
            encoding_bytes = face_service.embedding_to_bytes(face.embedding)
            is_primary = (
                db.query(FaceEncoding)
                .filter(FaceEncoding.employee_id == employee_id)
                .count()
                == 0
            )

            face_enc = FaceEncoding(
                employee_id=employee_id,
                encoding=encoding_bytes,
                image_path=str(image_path),
                quality_score=face.quality_score,
                is_primary=is_primary,
            )
            db.add(face_enc)
            db.commit()
            db.refresh(face_enc)

            # Add to FAISS index
            face_index_mgr.add_face(
                employee_id=employee_id,
                encoding_id=face_enc.id,
                embedding=face.embedding,
            )

            registered.append({
                "encoding_id": face_enc.id,
                "quality_score": face.quality_score,
                "det_score": face.det_score,
                "image_path": str(image_path),
            })

        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            errors.append(f"File {file.filename}: Processing error - {str(e)}")

    if not registered and errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "No faces registered", "errors": errors},
        )

    return {
        "message": f"Registered {len(registered)} face(s) for {employee.full_name}",
        "registered": registered,
        "errors": errors,
    }


@router.post("/verify")
async def verify_face(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Verify a face against the database.
    Upload an image and get the matching employee.
    Does not require authentication (used by the camera system).
    """
    face_service = _get_face_service()
    face_index_mgr = _get_face_index()

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format",
        )

    faces = face_service.detect_faces(frame)
    if not faces:
        return {"identified": False, "message": "No face detected"}

    results = []
    for face in faces:
        matches = face_index_mgr.search(
            face.embedding, threshold=settings.FACE_RECOGNITION_THRESHOLD
        )

        if matches:
            emp_id, similarity = matches[0]
            employee = db.query(Employee).filter(Employee.id == emp_id).first()
            if employee:
                results.append({
                    "employee_id": employee.id,
                    "employee_code": employee.employee_code,
                    "employee_name": employee.full_name,
                    "similarity": round(similarity, 4),
                    "bbox": face.bbox.tolist(),
                })

    return {
        "identified": len(results) > 0,
        "results": results,
        "total_faces_detected": len(faces),
    }


@router.delete("/face/{encoding_id}")
def delete_face_encoding(
    encoding_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a specific face encoding."""
    encoding = (
        db.query(FaceEncoding).filter(FaceEncoding.id == encoding_id).first()
    )
    if not encoding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Face encoding not found",
        )

    employee_id = encoding.employee_id

    # Remove image file
    if encoding.image_path:
        image_path = Path(encoding.image_path)
        if image_path.exists():
            image_path.unlink()

    db.delete(encoding)
    db.commit()

    # Rebuild FAISS index for this employee
    face_index_mgr = _get_face_index()
    face_index_mgr.remove_employee_faces(employee_id)

    # Re-add remaining faces
    remaining = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id)
        .all()
    )
    face_service = _get_face_service()
    for enc in remaining:
        embedding = face_service.bytes_to_embedding(enc.encoding)
        face_index_mgr.add_face(employee_id, enc.id, embedding)

    return {"message": "Face encoding deleted"}


@router.get("/faces/{employee_id}")
def get_employee_faces(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all face encodings for an employee."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    encodings = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id)
        .order_by(FaceEncoding.created_at.desc())
        .all()
    )

    return {
        "employee_id": employee_id,
        "employee_name": employee.full_name,
        "faces": [
            {
                "id": enc.id,
                "quality_score": enc.quality_score,
                "is_primary": enc.is_primary,
                "image_path": enc.image_path,
                "created_at": enc.created_at.isoformat() if enc.created_at else None,
            }
            for enc in encodings
        ],
    }


@router.get("/status")
def recognition_status(current_user=Depends(get_current_user)):
    """Get face recognition system status."""
    face_service = _get_face_service()
    face_index_mgr = _get_face_index()

    return {
        "model_loaded": face_service.is_initialized,
        "model_name": face_service.model_name,
        "provider_configured": settings.FACE_ONNX_PROVIDER,
        "provider_active": face_service.active_provider,
        "providers_active": face_service.active_providers,
        "using_gpu": face_service.is_using_gpu,
        "index_initialized": face_index_mgr.is_initialized,
        "total_faces_indexed": face_index_mgr.total_faces,
        "total_employees_indexed": face_index_mgr.total_employees,
        "recognition_threshold": settings.FACE_RECOGNITION_THRESHOLD,
        "detection_threshold": settings.FACE_DETECTION_THRESHOLD,
        "anti_spoofing_enabled": settings.ANTI_SPOOFING_ENABLED,
        "anti_spoofing_interval_frames": settings.ANTI_SPOOFING_INTERVAL_FRAMES,
    }
