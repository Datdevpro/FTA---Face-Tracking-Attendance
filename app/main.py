"""
FTA - Face Time Attendance System
Main FastAPI application entry point.

This module initializes all services, registers routes,
and configures the application lifecycle.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.database import engine, Base, SessionLocal
from app.models.department import Department
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.models.attendance import AttendanceRecord, WorkSchedule
from app.models.user import AdminUser, SystemLog
from app.services.face_recognition import FaceRecognitionService
from app.services.face_index import FaceIndexManager
from app.services.anti_spoofing import AntiSpoofingService
from app.services.attendance_service import AttendanceService
from app.services.camera_service import CameraService

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global service instances
# ---------------------------------------------------------------------------
face_service = FaceRecognitionService(
    model_name=settings.FACE_MODEL_NAME,
    models_dir=settings.MODELS_DIR,
)
face_index = FaceIndexManager(index_dir=settings.FAISS_INDEX_DIR)
anti_spoofing = AntiSpoofingService(threshold=settings.ANTI_SPOOFING_THRESHOLD)
attendance_service = AttendanceService()
camera_service = CameraService(
    source=settings.camera_source_parsed,
    width=settings.CAMERA_WIDTH,
    height=settings.CAMERA_HEIGHT,
    fps=settings.CAMERA_FPS,
)


def _rebuild_faiss_index():
    """Load all face encodings from DB and rebuild FAISS index."""
    db = SessionLocal()
    try:
        encodings = db.query(FaceEncoding).all()
        if not encodings:
            face_index.build_index([])
            return

        embeddings_data = []
        for enc in encodings:
            embedding = face_service.bytes_to_embedding(enc.encoding)
            embeddings_data.append({
                "employee_id": enc.employee_id,
                "encoding_id": enc.id,
                "embedding": embedding,
            })

        face_index.build_index(embeddings_data)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # --- Startup ---
    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)

    # Ensure directories exist
    settings.ensure_directories()

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Create default admin user if not exists
    _ensure_default_admin()

    # Initialize face recognition model
    try:
        face_service.initialize()
    except Exception as e:
        logger.warning(
            f"Face recognition model not loaded: {e}. "
            f"Install insightface and download models to enable."
        )

    # Initialize and rebuild FAISS index
    try:
        _rebuild_faiss_index()
    except Exception as e:
        logger.warning(f"FAISS index initialization failed: {e}")

    logger.info("Application startup complete")
    logger.info(f"Dashboard: http://localhost:{settings.PORT}")
    logger.info(f"API Docs:  http://localhost:{settings.PORT}/docs")

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    camera_service.stop()
    logger.info("Application shutdown complete")


def _ensure_default_admin():
    """Create a default admin user if no admin exists."""
    from app.core.security import hash_password

    db = SessionLocal()
    try:
        admin_count = db.query(AdminUser).count()
        if admin_count == 0:
            admin = AdminUser(
                username="admin",
                hashed_password=hash_password("admin123"),
                full_name="System Administrator",
                role="ADMIN",
            )
            db.add(admin)
            db.commit()
            logger.info("Default admin user created (admin / admin123)")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Face Recognition Time Attendance System for Small Business",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount static files (frontend)
# ---------------------------------------------------------------------------
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(frontend_dir)),
        name="static",
    )

# Mount face images for display
face_images_dir = Path(settings.FACE_IMAGES_DIR)
face_images_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/face-images",
    StaticFiles(directory=str(face_images_dir)),
    name="face-images",
)

# ---------------------------------------------------------------------------
# Register API routers
# ---------------------------------------------------------------------------
from app.api.auth import router as auth_router
from app.api.departments import router as departments_router
from app.api.employees import router as employees_router
from app.api.recognition import router as recognition_router
from app.api.attendance import router as attendance_router
from app.api.reports import router as reports_router

app.include_router(auth_router)
app.include_router(departments_router)
app.include_router(employees_router)
app.include_router(recognition_router)
app.include_router(attendance_router)
app.include_router(reports_router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws/camera-stream")
async def websocket_camera_stream(websocket: WebSocket):
    """WebSocket endpoint for live camera recognition stream."""
    from app.websocket.camera_stream import camera_stream_handler

    # Start camera if not running
    if not camera_service.is_running:
        camera_service.start()

    await camera_stream_handler(
        websocket=websocket,
        face_service=face_service,
        face_index=face_index,
        anti_spoofing=anti_spoofing,
        attendance_service=attendance_service,
        camera_service=camera_service,
    )


# ---------------------------------------------------------------------------
# Root & Health endpoints
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    """Redirect to dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/api/health", tags=["System"])
def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "face_model_loaded": face_service.is_initialized,
        "faiss_index_faces": face_index.total_faces,
        "camera_connected": camera_service.is_connected,
    }


@app.get("/api/camera/status", tags=["System"])
def camera_status():
    """Get camera status."""
    return camera_service.get_status()


@app.post("/api/camera/start", tags=["System"])
async def start_camera():
    """Start the camera capture (non-blocking)."""
    if camera_service.is_running:
        return {"message": "Camera already running"}
    # Run camera connection in background thread so it doesn't block the event loop
    await asyncio.get_event_loop().run_in_executor(None, camera_service.start)
    return {"message": "Camera started", "status": camera_service.get_status()}


@app.post("/api/camera/stop", tags=["System"])
def stop_camera():
    """Stop the camera capture."""
    camera_service.stop()
    return {"message": "Camera stopped"}


# ---------------------------------------------------------------------------
# Run with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
