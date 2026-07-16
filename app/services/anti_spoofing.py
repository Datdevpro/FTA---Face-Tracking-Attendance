"""ONNX-based face anti-spoofing service."""

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AntiSpoofingService:
    """Classify an InsightFace face crop as live or spoof."""

    LIVE_CLASS_INDEX = 0

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        onnx_provider: str = "cuda",
        crop_scale: float = 1.5,
    ):
        if not 0.0 < threshold < 1.0:
            raise ValueError("Anti-spoofing threshold must be between 0 and 1")
        if crop_scale < 1.0:
            raise ValueError("Anti-spoofing crop scale must be at least 1.0")

        self.model_path = Path(model_path)
        self.threshold = threshold
        self.onnx_provider = onnx_provider
        self.crop_scale = crop_scale
        self.active_provider: Optional[str] = None
        self.active_providers = []
        self.input_name: Optional[str] = None
        self.input_size = 128
        self.last_error: Optional[str] = None
        self._session = None

    @property
    def is_initialized(self) -> bool:
        return self._session is not None

    @property
    def is_using_gpu(self) -> bool:
        return self.active_provider == "CUDAExecutionProvider"

    def initialize(self) -> None:
        """Load and validate the ONNX model once during application startup."""
        if self.is_initialized:
            return
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Anti-spoofing model not found: {self.model_path}")

        import onnxruntime as ort

        available = ort.get_available_providers()
        requested = (self.onnx_provider or "cuda").strip().lower()
        use_cuda = (
            requested in {"cuda", "gpu", "auto"}
            and "CUDAExecutionProvider" in available
        )
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if use_cuda
            else ["CPUExecutionProvider"]
        )

        if requested in {"cuda", "gpu"} and not use_cuda:
            logger.warning(
                "CUDAExecutionProvider is unavailable for anti-spoofing; using CPU."
            )

        try:
            self._create_session(ort, providers)
        except Exception:
            if not use_cuda:
                raise
            logger.exception(
                "CUDA anti-spoofing initialization failed; retrying on CPU."
            )
            self._create_session(ort, ["CPUExecutionProvider"])

        logger.info(
            "Anti-spoofing model loaded: %s (provider=%s, input=%dx%d)",
            self.model_path,
            self.active_provider,
            self.input_size,
            self.input_size,
        )

    def _create_session(self, ort, providers) -> None:
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=providers,
        )

        model_input = session.get_inputs()[0]
        input_shape = model_input.shape
        if len(input_shape) != 4 or input_shape[1] != 3:
            raise ValueError(
                f"Unsupported anti-spoofing input shape: {input_shape}"
            )
        if isinstance(input_shape[-1], int):
            self.input_size = input_shape[-1]

        output_shape = session.get_outputs()[0].shape
        if len(output_shape) != 2 or output_shape[-1] != 2:
            raise ValueError(
                f"Unsupported anti-spoofing output shape: {output_shape}"
            )

        self._session = session
        self.input_name = model_input.name
        self.active_providers = session.get_providers()
        self.active_provider = self.active_providers[0]
        self.last_error = None

    def check_liveness(
        self,
        frame: np.ndarray,
        bbox: np.ndarray,
    ) -> Tuple[bool, float]:
        """Return ``(is_live, live_probability)`` for one detected face."""
        if not self.is_initialized:
            logger.error("Anti-spoofing inference requested before model initialization")
            return False, 0.0

        try:
            face_crop = self._crop_face(frame, bbox)
            if face_crop is None:
                return False, 0.0

            input_tensor = self._preprocess(face_crop)
            logits = self._session.run(
                None, {self.input_name: input_tensor}
            )[0]
            probabilities = self._softmax(np.asarray(logits).reshape(-1))
            if probabilities.size != 2:
                raise ValueError(
                    f"Expected 2 anti-spoofing scores, got {probabilities.size}"
                )

            live_score = float(probabilities[self.LIVE_CLASS_INDEX])
            predicted_class = int(np.argmax(probabilities))
            is_live = (
                predicted_class == self.LIVE_CLASS_INDEX
                and live_score >= self.threshold
            )
            self.last_error = None
            return is_live, live_score
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Anti-spoofing inference failed")
            return False, 0.0

    def _crop_face(
        self, frame: np.ndarray, bbox: np.ndarray
    ) -> Optional[np.ndarray]:
        if frame is None or frame.size == 0 or len(bbox) < 4:
            return None

        x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
        face_width = x2 - x1
        face_height = y2 - y1
        if face_width <= 0 or face_height <= 0:
            return None

        side = max(face_width, face_height) * self.crop_scale
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        crop_x1 = int(np.floor(center_x - side / 2.0))
        crop_y1 = int(np.floor(center_y - side / 2.0))
        crop_x2 = int(np.ceil(center_x + side / 2.0))
        crop_y2 = int(np.ceil(center_y + side / 2.0))

        frame_height, frame_width = frame.shape[:2]
        clipped_x1 = max(0, crop_x1)
        clipped_y1 = max(0, crop_y1)
        clipped_x2 = min(frame_width, crop_x2)
        clipped_y2 = min(frame_height, crop_y2)
        if clipped_x2 <= clipped_x1 or clipped_y2 <= clipped_y1:
            return None

        crop = frame[clipped_y1:clipped_y2, clipped_x1:clipped_x2]
        return cv2.copyMakeBorder(
            crop,
            clipped_y1 - crop_y1,
            crop_y2 - clipped_y2,
            clipped_x1 - crop_x1,
            crop_x2 - clipped_x2,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0),
        )

    def _preprocess(self, face_crop: np.ndarray) -> np.ndarray:
        rgb_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(
            rgb_crop,
            (self.input_size, self.input_size),
            interpolation=cv2.INTER_LINEAR,
        )
        tensor = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(tensor, axis=0)

    @staticmethod
    def _softmax(values: np.ndarray) -> np.ndarray:
        shifted = values - np.max(values)
        exp_values = np.exp(shifted)
        return exp_values / np.sum(exp_values)
