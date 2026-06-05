"""
Camera Service for managing video capture from USB or IP cameras.
"""

import logging
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraService:
    """
    Manages camera capture with thread-safe frame access.

    Supports:
    - USB webcams (by index: 0, 1, 2...)
    - IP cameras (RTSP/HTTP URL)
    - Auto-reconnect on connection loss
    """

    def __init__(
        self,
        source=0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._starting = False
        self._last_frame_time = 0.0
        self._frame_count = 0

    def start(self):
        """Start the camera capture thread without blocking on device connection."""
        if self._running:
            return

        self._running = True
        self._starting = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera starting: source={self.source}")

    def stop(self):
        """Stop the camera capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        self._disconnect()
        self._starting = False
        self._frame_count = 0
        self._last_frame_time = 0.0
        logger.info("Camera stopped")

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get the latest captured frame (thread-safe).

        Returns:
            BGR image as numpy array, or None if no frame available.
        """
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def capture_single_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame without the background thread.
        Useful for one-off captures (e.g., face registration).
        """
        if not self._connected:
            self._connect()

        if self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                return frame
        return None

    def _connect(self):
        """Connect to the camera."""
        try:
            if isinstance(self.source, int) and sys.platform.startswith("win"):
                self._cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            else:
                self._cap = cv2.VideoCapture(self.source)
            if isinstance(self.source, int):
                # USB camera settings
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.fps)
                # Reduce buffer size for lower latency
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._connected = self._cap.isOpened()
            if self._connected:
                self._starting = False
                logger.info(f"Camera connected: {self.source}")
            else:
                self._starting = False
                logger.warning(f"Camera not available: {self.source}")
        except Exception as e:
            logger.error(f"Camera connection error: {e}")
            self._connected = False
            self._starting = False

    def _disconnect(self):
        """Release camera resources."""
        if self._cap:
            self._cap.release()
            self._cap = None
        self._connected = False
        with self._lock:
            self._frame = None

    def _capture_loop(self):
        """Background thread that continuously captures frames."""
        reconnect_delay = 2.0
        frame_interval = 1.0 / self.fps

        while self._running:
            if not self._connected or not self._cap or not self._cap.isOpened():
                logger.warning("Camera disconnected. Reconnecting...")
                self._starting = True
                self._connect()
                if not self._connected:
                    time.sleep(reconnect_delay)
                continue

            try:
                ret, frame = self._cap.read()
                if ret:
                    with self._lock:
                        self._frame = frame
                    self._last_frame_time = time.time()
                    self._frame_count += 1
                else:
                    self._connected = False
                    logger.warning("Failed to read frame, will reconnect")
            except Exception as e:
                logger.error(f"Capture error: {e}")
                self._connected = False

            # Frame rate control
            time.sleep(frame_interval)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_starting(self) -> bool:
        return self._starting and not self._connected

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def get_status(self) -> dict:
        """Get camera status info."""
        return {
            "source": str(self.source),
            "connected": self._connected,
            "running": self._running,
            "starting": self.is_starting,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "frame_count": self._frame_count,
        }
