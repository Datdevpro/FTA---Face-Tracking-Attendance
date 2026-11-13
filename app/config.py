"""
FTA - Face Time Attendance System
Application configuration loaded from environment variables.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # --- Application ---
    APP_NAME: str = "FTA - Face Time Attendance"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Database ---
    # SQLite is the temporary local default.
    # PostgreSQL option for later:
    # DATABASE_URL: str = "postgresql://fta_user:fta_password@localhost:5432/fta_db"
    DATABASE_URL: str = "sqlite:///./data/fta.db"
    DB_ECHO: bool = False

    # --- JWT Authentication ---
    JWT_SECRET_KEY: str = "fta-dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # --- Camera ---
    CAMERA_SOURCE: str = "0"
    CAMERA_IMOU_ROTATE_RTSP: str = ""
    CAMERA_IMOU_FIXED_RTSP: str = ""
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    CAMERA_FPS: int = 30
    RTSP_OPEN_TIMEOUT_MS: int = Field(default=5000, gt=0)
    RTSP_READ_TIMEOUT_MS: int = Field(default=5000, gt=0)
    STREAM_PREVIEW_FPS: int = 15
    RECOGNITION_INTERVAL_FRAMES: int = 5
    RECOGNITION_MAX_STALE_MS: int = 1000

    # --- Face Recognition ---
    FACE_MODEL_NAME: str = "buffalo_l"
    FACE_ONNX_PROVIDER: str = "cuda"
    FACE_DETECTION_THRESHOLD: float = 0.5
    FACE_RECOGNITION_THRESHOLD: float = 0.5
    FACE_MIN_QUALITY: float = 0.3
    FACE_REGISTRATION_COUNT: int = 3

    # --- Anti-Spoofing ---
    ANTI_SPOOFING_ENABLED: bool = True
    ANTI_SPOOFING_MODEL_PATH: str = (
        "./data/models/anti_spoofing/AntiSpoofing_bin_1.5_128.onnx"
    )
    ANTI_SPOOFING_PROVIDER: str = "cuda"
    ANTI_SPOOFING_THRESHOLD: float = 0.5
    ANTI_SPOOFING_CROP_SCALE: float = 1.5
    ANTI_SPOOFING_INTERVAL_FRAMES: int = 5

    # --- Attendance ---
    WORK_START_TIME: str = "08:30"
    WORK_END_TIME: str = "17:30"
    LATE_THRESHOLD_MINUTES: int = 15
    CHECK_OUT_WINDOW_MINUTES: int = 15
    ATTENDANCE_PENDING_STATE_PATH: str = "./data/pending_checkouts.json"

    # --- File Storage ---
    FACE_IMAGES_DIR: str = "./data/face_images"
    FAISS_INDEX_DIR: str = "./data/faiss_index"
    MODELS_DIR: str = "./data/models"
    ATTENDANCE_SNAPSHOTS_DIR: str = "./data/snapshots"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    @property
    def camera_source_parsed(self):
        """Parse camera source: integer for USB, string for RTSP URL."""
        try:
            return int(self.CAMERA_SOURCE)
        except ValueError:
            return self.CAMERA_SOURCE

    def camera_source_for(self, camera_id: str | None):
        """Resolve a named camera on the server; never accept URLs from clients."""
        if camera_id is None:
            return self.camera_source_parsed  # Legacy clients still use CAMERA_SOURCE.
        if camera_id == "webcam":
            return 0
        presets = {
            "imou_rotate": ("Cam IMOU xoay", self.CAMERA_IMOU_ROTATE_RTSP,
                            "CAMERA_IMOU_ROTATE_RTSP"),
            "imou_fixed": ("Cam IMOU cứng", self.CAMERA_IMOU_FIXED_RTSP,
                           "CAMERA_IMOU_FIXED_RTSP"),
        }
        if camera_id not in presets:
            raise ValueError("Nguồn camera không hợp lệ.")
        label, source, variable = presets[camera_id]
        source = source.strip()
        if not source:
            raise ValueError(f"Chưa cấu hình {label}. Hãy nhập {variable} trong .env rồi khởi động lại backend.")
        if not source.lower().startswith(("rtsp://", "rtsps://")):
            raise ValueError(f"{variable} phải là URL RTSP hợp lệ.")
        return source

    def ensure_directories(self):
        """Create all required data directories if they don't exist."""
        dirs = [
            self.FACE_IMAGES_DIR,
            self.FAISS_INDEX_DIR,
            self.MODELS_DIR,
            self.ATTENDANCE_SNAPSHOTS_DIR,
        ]
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton settings instance
settings = Settings()
