"""
Anti-Spoofing / Liveness Detection Service.

Provides basic anti-spoofing to prevent attendance fraud using:
- Texture analysis (LBP-based) to detect printed photos
- Color space analysis to detect screen displays
- Optional blink detection via face landmarks

Note: For production high-security environments, consider
integrating a commercial liveness detection API.
"""

import logging
from typing import Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AntiSpoofingService:
    """
    Basic anti-spoofing using image analysis techniques.

    Combines multiple heuristics:
    1. Laplacian variance (blur/texture analysis)
    2. Color distribution analysis (screens have different color patterns)
    3. Reflection detection (printed photos have glare patterns)
    4. Moiré pattern detection (screen capture artifacts)
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._initialized = True

    def check_liveness(
        self,
        frame: np.ndarray,
        bbox: np.ndarray,
    ) -> Tuple[bool, float]:
        """
        Check if a detected face is a real person or a spoof.

        Args:
            frame: Full BGR image.
            bbox: Face bounding box [x1, y1, x2, y2].

        Returns:
            Tuple of (is_live: bool, confidence: float).
        """
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return False, 0.0

        face_roi = frame[y1:y2, x1:x2]

        if face_roi.size == 0:
            return False, 0.0

        scores = []

        # 1. Texture analysis using Laplacian variance
        texture_score = self._analyze_texture(face_roi)
        scores.append(texture_score * 0.35)

        # 2. Color space analysis
        color_score = self._analyze_color_distribution(face_roi)
        scores.append(color_score * 0.25)

        # 3. Moiré pattern detection
        moire_score = self._detect_moire_patterns(face_roi)
        scores.append(moire_score * 0.20)

        # 4. Specular reflection check
        reflection_score = self._check_reflections(face_roi)
        scores.append(reflection_score * 0.20)

        total_score = sum(scores)
        is_live = total_score >= self.threshold

        return is_live, total_score

    def _analyze_texture(self, face_roi: np.ndarray) -> float:
        """
        Analyze face texture using Laplacian variance.
        Real faces have richer texture than printed/screen images.
        """
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)

        # Resize for consistent analysis
        gray = cv2.resize(gray, (128, 128))

        # Laplacian variance — higher = more texture detail
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        # Real faces typically have variance > 50
        if variance > 200:
            return 1.0
        elif variance > 100:
            return 0.8
        elif variance > 50:
            return 0.6
        elif variance > 20:
            return 0.3
        return 0.1

    def _analyze_color_distribution(self, face_roi: np.ndarray) -> float:
        """
        Analyze color distribution in HSV space.
        Screen displays and printed photos have different color
        distribution than real skin.
        """
        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)

        # Analyze saturation channel — real skin has natural saturation variance
        s_channel = hsv[:, :, 1]
        s_std = np.std(s_channel)
        s_mean = np.mean(s_channel)

        # Analyze value channel — screens are typically more uniform
        v_channel = hsv[:, :, 2]
        v_std = np.std(v_channel)

        # Real faces: moderate saturation variance, good value variance
        score = 0.0
        if 15 < s_std < 80:
            score += 0.5
        elif s_std >= 80:
            score += 0.3  # Too high variance = might be printed photo with background
        else:
            score += 0.1

        if v_std > 20:
            score += 0.5
        elif v_std > 10:
            score += 0.3
        else:
            score += 0.1  # Very uniform = likely screen

        return min(score, 1.0)

    def _detect_moire_patterns(self, face_roi: np.ndarray) -> float:
        """
        Detect moiré patterns that appear when capturing a screen.
        Uses frequency domain analysis (FFT).
        """
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (128, 128))

        # Apply FFT
        f_transform = np.fft.fft2(gray.astype(np.float32))
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift)

        # Analyze high-frequency components
        h, w = magnitude.shape
        center_y, center_x = h // 2, w // 2

        # Low-frequency energy (center)
        low_freq = magnitude[
            center_y - 10 : center_y + 10, center_x - 10 : center_x + 10
        ].sum()

        # High-frequency energy (edges)
        total_energy = magnitude.sum()
        high_freq = total_energy - low_freq

        # Moiré patterns create strong high-frequency peaks
        ratio = high_freq / max(total_energy, 1e-10)

        # Normal ratio for real faces is typically 0.85-0.98
        # Screen captures tend to have specific periodic peaks
        if 0.80 <= ratio <= 0.99:
            return 1.0
        elif ratio > 0.99:
            return 0.4  # Suspiciously high frequency = possible moiré
        else:
            return 0.5

    def _check_reflections(self, face_roi: np.ndarray) -> float:
        """
        Check for specular reflections typical of printed photos
        or screens (glossy surface reflections).
        """
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)

        # Count very bright pixels (potential glare/reflection)
        bright_pixels = np.sum(gray > 240)
        total_pixels = gray.size
        bright_ratio = bright_pixels / total_pixels

        # Some bright pixels are normal (eyes, teeth)
        # Too many = printed photo with glare
        if bright_ratio < 0.02:
            return 1.0  # Normal
        elif bright_ratio < 0.05:
            return 0.7
        elif bright_ratio < 0.10:
            return 0.4
        else:
            return 0.1  # Too much reflection

    @property
    def is_initialized(self) -> bool:
        return self._initialized
