"""
Face Recognition Service using InsightFace (SCRFD + ArcFace).

This is the core AI engine that handles:
- Face detection using SCRFD detector
- Face embedding extraction using ArcFace (buffalo_l model)
- Face quality assessment
"""

import logging
import os
import site
import time
import ctypes
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# InsightFace is imported lazily to avoid import errors during testing
_insightface = None
_app = None
_dll_directory_handles = []
_preloaded_cuda_dlls = []


def _get_insightface():
    """Lazy import of insightface module."""
    global _insightface
    if _insightface is None:
        import insightface

        _insightface = insightface
    return _insightface


def _prepare_cuda_dll_search_path(ort):
    """Make CUDA/cuDNN DLLs discoverable for ONNX Runtime on Windows."""
    if not hasattr(os, "add_dll_directory"):
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        return

    candidate_dirs = []

    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        candidate_dirs.append(Path(cuda_path) / "bin")

    for site_path in site.getsitepackages():
        nvidia_path = Path(site_path) / "nvidia"
        if not nvidia_path.exists():
            continue
        candidate_dirs.extend(path for path in nvidia_path.glob("*\\bin") if path.is_dir())

    seen = set()
    for path in candidate_dirs:
        resolved = str(path.resolve())
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        _dll_directory_handles.append(os.add_dll_directory(resolved))

    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    new_path_entries = [path for path in seen if path not in path_entries]
    if new_path_entries:
        os.environ["PATH"] = os.pathsep.join([*new_path_entries, *path_entries])

    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls()

    for directory in seen:
        for dll_path in sorted(Path(directory).glob("cudnn*.dll")):
            try:
                _preloaded_cuda_dlls.append(ctypes.WinDLL(str(dll_path)))
            except OSError as exc:
                logger.warning(f"Could not preload CUDA DLL {dll_path}: {exc}")


class FaceInfo:
    """Data class for a detected face."""

    def __init__(
        self,
        bbox: np.ndarray,
        embedding: np.ndarray,
        landmark: Optional[np.ndarray] = None,
        det_score: float = 0.0,
        quality_score: float = 0.0,
    ):
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.embedding = embedding  # 512-dim normalized vector
        self.landmark = landmark  # 5 facial landmarks
        self.det_score = det_score  # Detection confidence
        self.quality_score = quality_score  # Face quality score


class FaceRecognitionService:
    """
    Face recognition service using InsightFace.

    Uses SCRFD for detection and ArcFace (buffalo_l) for embedding.
    The model is loaded once at startup and reused for all requests.
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        models_dir: str = "./data/models",
        det_size: int = 320,
        onnx_provider: str = "cpu",
    ):
        self.model_name = model_name
        self.models_dir = models_dir
        self.det_size = det_size
        self.onnx_provider = onnx_provider
        self.active_provider = None
        self.active_providers = []
        self._app = None
        self._initialized = False

    def initialize(self):
        """
        Load the InsightFace model. Should be called once at startup.
        Downloads the model automatically if not present.
        """
        if self._initialized:
            return

        logger.info(f"Loading InsightFace model: {self.model_name}")
        start = time.time()

        insightface = _get_insightface()
        models_path = Path(self.models_dir)
        models_path.mkdir(parents=True, exist_ok=True)

        # Detect GPU support via onnxruntime
        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        logger.info(f"Available ONNX Runtime providers: {available_providers}")

        requested_provider = (self.onnx_provider or "cpu").strip().lower()
        if requested_provider in {"cuda", "gpu", "auto"} and "CUDAExecutionProvider" in available_providers:
            _prepare_cuda_dll_search_path(ort)
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            ctx_id = 0
            logger.info("Using GPU for face recognition inference (CUDAExecutionProvider).")
        else:
            providers = ["CPUExecutionProvider"]
            ctx_id = -1
            if requested_provider in {"cuda", "gpu"}:
                logger.warning("CUDAExecutionProvider is not available; using CPUExecutionProvider instead.")
            logger.info("Using CPU for face recognition inference (CPUExecutionProvider).")

        try:
            self._prepare_app(insightface, models_path, providers, ctx_id)
        except Exception:
            if providers[0] != "CUDAExecutionProvider":
                raise
            logger.exception("CUDA model initialization failed; retrying with CPUExecutionProvider.")
            providers = ["CPUExecutionProvider"]
            ctx_id = -1
            self._prepare_app(insightface, models_path, providers, ctx_id)

        self.active_providers = providers
        self.active_provider = providers[0]
        elapsed = time.time() - start
        logger.info(f"InsightFace model loaded in {elapsed:.2f}s (det_size={self.det_size}, ctx_id={ctx_id})")
        self._initialized = True

    def _prepare_app(self, insightface, models_path: Path, providers: List[str], ctx_id: int):
        self._app = insightface.app.FaceAnalysis(
            name=self.model_name,
            root=str(models_path),
            providers=providers,
        )
        # det_size=(320,320) is much faster than (640,640) on CPU
        # with minimal accuracy loss for close-range face detection
        self._app.prepare(ctx_id=ctx_id, det_size=(self.det_size, self.det_size))

    def detect_faces(
        self,
        frame: np.ndarray,
        min_det_score: float = 0.5,
    ) -> List[FaceInfo]:
        """
        Detect faces in a frame and extract embeddings.

        Args:
            frame: BGR image (OpenCV format).
            min_det_score: Minimum detection confidence threshold.

        Returns:
            List of FaceInfo objects with bboxes and embeddings.
        """
        if not self._initialized:
            self.initialize()

        faces = self._app.get(frame)
        results = []

        for face in faces:
            det_score = float(face.det_score)
            if det_score < min_det_score:
                continue

            # Calculate face quality based on multiple factors
            quality = self._assess_quality(face, frame)

            face_info = FaceInfo(
                bbox=face.bbox.astype(np.int32),
                embedding=face.normed_embedding,
                landmark=face.landmark_2d_106 if hasattr(face, "landmark_2d_106") else face.kps,
                det_score=det_score,
                quality_score=quality,
            )
            results.append(face_info)

        return results

    def extract_embedding(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract face embedding from a frame containing exactly one face.

        Args:
            frame: BGR image with a single face.

        Returns:
            512-dim normalized embedding vector, or None if no face detected.
        """
        faces = self.detect_faces(frame)
        if not faces:
            return None
        # Return the face with highest detection score
        best_face = max(faces, key=lambda f: f.det_score)
        return best_face.embedding

    def _assess_quality(self, face, frame: np.ndarray) -> float:
        """
        Assess face quality based on multiple factors:
        - Detection confidence
        - Face size relative to frame
        - Face angle (using landmarks)
        - Blur estimation

        Returns:
            Quality score between 0.0 and 1.0.
        """
        scores = []

        # 1. Detection confidence (weight: 0.3)
        scores.append(float(face.det_score) * 0.3)

        # 2. Face size score (weight: 0.25)
        bbox = face.bbox
        face_width = bbox[2] - bbox[0]
        face_height = bbox[3] - bbox[1]
        frame_h, frame_w = frame.shape[:2]
        face_area_ratio = (face_width * face_height) / (frame_w * frame_h)
        # Ideal: face takes 5-30% of frame
        if face_area_ratio < 0.01:
            size_score = 0.2
        elif face_area_ratio < 0.05:
            size_score = 0.6
        elif face_area_ratio < 0.30:
            size_score = 1.0
        else:
            size_score = 0.8
        scores.append(size_score * 0.25)

        # 3. Face aspect ratio (weight: 0.15) — too wide/narrow = bad angle
        aspect = face_width / max(face_height, 1)
        if 0.65 <= aspect <= 0.85:
            aspect_score = 1.0
        elif 0.5 <= aspect <= 1.0:
            aspect_score = 0.7
        else:
            aspect_score = 0.3
        scores.append(aspect_score * 0.15)

        # 4. Blur estimation (weight: 0.3) — Laplacian variance
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame_w, x2), min(frame_h, y2)
        if x2 > x1 and y2 > y1:
            face_roi = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            # Higher variance = sharper image
            if laplacian_var > 200:
                blur_score = 1.0
            elif laplacian_var > 100:
                blur_score = 0.8
            elif laplacian_var > 50:
                blur_score = 0.5
            else:
                blur_score = 0.2
        else:
            blur_score = 0.0
        scores.append(blur_score * 0.3)

        return min(sum(scores), 1.0)

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two face embeddings.

        Args:
            embedding1: 512-dim normalized vector.
            embedding2: 512-dim normalized vector.

        Returns:
            Similarity score (0.0 to 1.0, higher = more similar).
        """
        return float(np.dot(embedding1, embedding2))

    @staticmethod
    def embedding_to_bytes(embedding: np.ndarray) -> bytes:
        """Convert numpy embedding to bytes for database storage."""
        return embedding.astype(np.float32).tobytes()

    @staticmethod
    def bytes_to_embedding(data: bytes) -> np.ndarray:
        """Convert bytes back to numpy embedding."""
        return np.frombuffer(data, dtype=np.float32).copy()

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_using_gpu(self) -> bool:
        return self.active_provider == "CUDAExecutionProvider"
