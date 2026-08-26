"""Detect and recognize faces from a USB camera using this repository's SDK.

Enhanced Features:
  - Face detection       (face_detect)
  - Facial landmark detection  (face_landmark)
  - Face feature / embedding extraction  (face_feature)
  - Face pose estimation - yaw / pitch / roll  (face_pose)
  - Aligned-face thumbnail panel
  - Real-time FPS counter
  - Multi-face support with per-face identity labels and similarity bars
  - Live face registration from camera: press R
  - Live face registration from image file: press U (opens file dialog)
  - Press Q or Esc to quit

Usage:
    python camera_detect.py [--camera 0] [--width 640] [--height 480]
                            [--max-faces 5] [--known-dir known_faces]
                            [--threshold 75.0]
"""

import argparse
import os
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

# tkinter is used for the native file-picker dialog (Upload feature)
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    _TK_AVAILABLE = True
except ImportError:
    _TK_AVAILABLE = False


# ---------------------------------------------------------------------------
# SDK root must be the CWD so that model-weight paths resolve correctly.
# ---------------------------------------------------------------------------
SDK_ROOT = Path(__file__).resolve().parent
os.chdir(SDK_ROOT)

from face_detect.detect_imgs import get_face_boundingbox   # noqa: E402
from face_feature.GetFeature import get_face_feature        # noqa: E402
from face_landmark.GetLandmark import get_face_landmark     # noqa: E402
from face_pose.GetPose import get_face_pose                 # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# UI colours (BGR)
COLOR_GREEN  = (0,   220,  80)
COLOR_RED    = (0,    60, 220)
COLOR_YELLOW = (0,   210, 255)
COLOR_CYAN   = (220, 220,   0)
COLOR_WHITE  = (255, 255, 255)
COLOR_DARK   = ( 20,  20,  20)
COLOR_GRAY   = (140, 140, 140)
COLOR_PANEL  = ( 30,  30,  30)

THUMBNAIL_SIZE = 80    # pixels - aligned-face thumbnail
PANEL_W        = 230   # right-side info panel width
BAR_MAX_W      = 140   # similarity bar max width
FONT           = cv2.FONT_HERSHEY_SIMPLEX


# ===========================================================================
# Argument parsing
# ===========================================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Enhanced face recognition from a USB camera"
    )
    parser.add_argument("--camera",    type=int,   default=0,
                        help="USB camera index (default: 0)")
    parser.add_argument("--width",     type=int,   default=640,
                        help="Capture width (default: 640)")
    parser.add_argument("--height",    type=int,   default=480,
                        help="Capture height (default: 480)")
    parser.add_argument("--max-faces", type=int,   default=5,
                        help="Maximum faces to process per frame (default: 5)")
    parser.add_argument("--known-dir", type=Path,  default=Path("known_faces"),
                        help="Folder of labelled reference images")
    parser.add_argument("--threshold", type=float, default=75.0,
                        help="Min similarity %% to count as a match (default: 75)")
    return parser.parse_args()


# ===========================================================================
# Camera helpers
# ===========================================================================
def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    """Open the USB camera, trying the OS-preferred backend first."""
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
    return cap


# ===========================================================================
# SDK wrappers
# ===========================================================================
def extract_landmark_and_feature(image: np.ndarray, box):
    """Return (landmark_np, aligned_face, feature_vec) for one bounding box."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    landmark = get_face_landmark(gray, box).detach().cpu().numpy()
    aligned_face, feature = get_face_feature(image, landmark)
    return landmark, aligned_face, feature


def extract_pose(box, landmark: np.ndarray) -> np.ndarray:
    """Return (yaw, pitch, roll) in degrees for a detected face."""
    try:
        pose = get_face_pose(box.detach().cpu().numpy(), landmark)
        return pose  # shape (3,) - [yaw, pitch, roll]
    except Exception:
        return np.zeros(3, dtype=np.float32)


# ===========================================================================
# Known-face database
# ===========================================================================
def reference_name(image_path: Path, known_dir: Path) -> str:
    rel = image_path.relative_to(known_dir)
    return rel.parts[0] if len(rel.parts) > 1 else image_path.stem


def load_known_faces(known_dir: Path) -> list:
    """
    Load every reference image in *known_dir* and extract its embedding.

    Returns:
        List of (name: str, feature: np.ndarray) tuples.
    """
    known_dir = known_dir.resolve()
    known_faces = []

    if not known_dir.is_dir():
        print(f"[INFO] Known-face folder not found: {known_dir}")
        print("[INFO] Create it and add images such as  known_faces/Alice.jpg")
        return known_faces

    image_paths = sorted(
        p for p in known_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        and not p.stem.endswith("_aligned")   # <-- Bỏ qua ảnh aligned preview
    )

    for image_path in image_paths:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            print(f"[WARN] Unreadable image skipped: {image_path}")
            continue

        boxes, scores = get_face_boundingbox(image)
        if len(boxes) == 0:
            print(f"[WARN] No face detected in: {image_path}")
            continue

        best_idx = int(np.argmax(scores.detach().cpu().numpy()))
        _, _, feature = extract_landmark_and_feature(image, boxes[best_idx])
        name = reference_name(image_path, known_dir)
        known_faces.append((name, feature))
        print(f"[INFO] Loaded: {name}  ({image_path.name})")

    print(f"[INFO] {len(known_faces)} reference face(s) loaded.")
    return known_faces


def save_known_face(
    known_dir: Path,
    name: str,
    image: np.ndarray,
    aligned_face: np.ndarray,
    feature: np.ndarray,
    known_faces: list,
) -> None:
    """
    Persist a newly registered face to disk and append it to *known_faces*.
    Both the raw face crop and the aligned thumbnail are saved.
    """
    known_dir.mkdir(parents=True, exist_ok=True)
    timestamp    = int(time.time())
    raw_path     = known_dir / f"{name}_{timestamp}.jpg"
    aligned_path = known_dir / f"{name}_{timestamp}_aligned.jpg"
    cv2.imwrite(str(raw_path),     image)
    cv2.imwrite(str(aligned_path), aligned_face)
    known_faces.append((name, feature))
    print(f"[INFO] Registered '{name}' -> {raw_path}")


def register_from_image_file(
    known_dir: Path,
    known_faces: list,
) -> str:
    """
    Open a native file-picker dialog, let the user choose an image, detect
    the face in it, prompt for a name, and register the embedding.

    Returns:
        The registered name on success, or an empty string on failure/cancel.
    """
    if not _TK_AVAILABLE:
        print("[ERROR] tkinter is not available — cannot open file dialog.")
        print("        Tip: install tkinter or place the image manually in the known_faces/ folder.")
        return ""

    # Hide the root Tk window — we only want the dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)   # bring dialog to front

    file_types = [
        ("Image files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"),
        ("All files",   "*.*"),
    ]
    image_path = filedialog.askopenfilename(
        title="Select a face image to register",
        filetypes=file_types,
    )
    root.destroy()

    if not image_path:
        print("[INFO] Upload cancelled — no file selected.")
        return ""

    image_path = Path(image_path)
    print(f"[UPLOAD] Selected: {image_path}")

    # Load and validate the image
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        print(f"[ERROR] Could not read image: {image_path}")
        return ""

    # Detect face
    boxes, scores = get_face_boundingbox(image)
    if len(boxes) == 0:
        print("[ERROR] No face detected in the selected image. Try a clearer photo.")
        return ""

    # Use the highest-confidence face
    best_idx = int(np.argmax(scores.detach().cpu().numpy()))
    box      = boxes[best_idx]

    try:
        _, aligned_face, feature = extract_landmark_and_feature(image, box)
    except Exception as exc:
        print(f"[ERROR] Feature extraction failed: {exc}")
        return ""

    # Crop the raw face for storage
    x1, y1, x2, y2 = box.detach().cpu().numpy().astype(int)
    h_img, w_img   = image.shape[:2]
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(w_img, x2); y2 = min(h_img, y2)
    face_crop = image[y1:y2, x1:x2].copy()

    # Prompt for name
    print("[UPLOAD] Enter name for this face: ", end="", flush=True)
    name = input().strip()
    if not name:
        print("[INFO] Upload registration cancelled (empty name).")
        return ""

    # Show a quick preview in a small window
    preview = cv2.resize(aligned_face, (192, 192))
    cv2.putText(preview, name, (6, 185), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 220, 80), 1, cv2.LINE_AA)
    cv2.imshow(f"Registered: {name}", preview)
    cv2.waitKey(1500)
    cv2.destroyWindow(f"Registered: {name}")

    save_known_face(known_dir.resolve(), name, face_crop, aligned_face, feature, known_faces)
    print(f"[INFO] '{name}' registered from image. Now testing via camera ...")
    return name


# ===========================================================================
# Face matching
# ===========================================================================
def recognize_face(
    feature: np.ndarray,
    known_faces: list,
    threshold: float,
):
    """Return (best_name, best_similarity_pct). Returns 'Unknown' when below threshold."""
    best_name  = "Unknown"
    best_score = 0.0
    for name, known_feat in known_faces:
        score = float((np.sum(known_feat * feature) + 1.0) * 50.0)
        if score > best_score:
            best_name  = name
            best_score = score
    if best_score < threshold:
        best_name = "Unknown"
    return best_name, best_score


# ===========================================================================
# Drawing / HUD helpers
# ===========================================================================
def _draw_rounded_rect(
    img: np.ndarray,
    pt1: tuple,
    pt2: tuple,
    color: tuple,
    thickness: int = 2,
    radius: int = 8,
) -> None:
    """Draw a rectangle with rounded corners."""
    x1, y1 = pt1
    x2, y2 = pt2
    cv2.line(img, (x1 + radius, y1),      (x2 - radius, y1),      color, thickness)
    cv2.line(img, (x1 + radius, y2),      (x2 - radius, y2),      color, thickness)
    cv2.line(img, (x1, y1 + radius),      (x1, y2 - radius),      color, thickness)
    cv2.line(img, (x2, y1 + radius),      (x2, y2 - radius),      color, thickness)
    cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius),  90, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius),   0, 0, 90, color, thickness)


def _text_shadow(
    img: np.ndarray,
    text: str,
    org: tuple,
    font_scale: float,
    color: tuple,
    thickness: int = 1,
) -> None:
    """Draw text with a dark shadow for readability on any background."""
    cv2.putText(img, text, (org[0] + 1, org[1] + 1), FONT, font_scale,
                COLOR_DARK, thickness + 1, cv2.LINE_AA)
    cv2.putText(img, text, org, FONT, font_scale, color, thickness, cv2.LINE_AA)


def _similarity_bar(
    img: np.ndarray,
    x: int,
    y: int,
    similarity: float,
    name: str,
) -> None:
    """Draw a labelled similarity percentage bar."""
    pct       = min(similarity, 100.0) / 100.0
    fill      = int(pct * BAR_MAX_W)
    bar_color = COLOR_GREEN if pct >= 0.75 else (COLOR_YELLOW if pct >= 0.55 else COLOR_RED)
    cv2.rectangle(img, (x, y), (x + BAR_MAX_W, y + 12), (50, 50, 50), -1)
    if fill > 0:
        cv2.rectangle(img, (x, y), (x + fill, y + 12), bar_color, -1)
    cv2.rectangle(img, (x, y), (x + BAR_MAX_W, y + 12), COLOR_GRAY, 1)
    _text_shadow(img, f"{name[:14]}  {similarity:.1f}%", (x, y - 3), 0.38, COLOR_WHITE)


def draw_face_box(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    name: str,
    similarity: float,
    det_score: float,
    pose: np.ndarray,
    index: int,
) -> None:
    """Draw a stylised bounding box with identity label and pose info."""
    is_known = name != "Unknown"
    color    = COLOR_GREEN if is_known else COLOR_RED

    # Semi-transparent fill
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)

    # Rounded border
    _draw_rounded_rect(frame, (x1, y1), (x2, y2), color, thickness=2, radius=10)

    # Corner accents (L-shaped)
    arm = 14
    for cx, cy, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(frame, (cx, cy), (cx + dx * arm, cy),          color, 2)
        cv2.line(frame, (cx, cy), (cx,             cy + dy * arm), color, 2)

    # Identity label pill
    label = f"#{index + 1} {name}"
    (lw, lh), _ = cv2.getTextSize(label, FONT, 0.55, 2)
    lx, ly = x1, max(0, y1 - lh - 10)
    cv2.rectangle(frame, (lx - 4, ly - 4), (lx + lw + 4, ly + lh + 4), color, -1)
    cv2.putText(frame, label, (lx, ly + lh), FONT, 0.55, COLOR_DARK, 2, cv2.LINE_AA)

    # Similarity % (top-right inside box)
    sim_txt = f"{similarity:.1f}%"
    (sw, _), _ = cv2.getTextSize(sim_txt, FONT, 0.45, 1)
    _text_shadow(frame, sim_txt, (x2 - sw - 4, y1 + 16), 0.45,
                 COLOR_GREEN if is_known else COLOR_YELLOW)

    # Detection confidence (bottom-left inside box)
    _text_shadow(frame, f"det:{det_score:.2f}", (x1 + 4, y2 - 6), 0.38, COLOR_CYAN)

    # Pose angles (just above detection score)
    yaw, pitch, roll = pose
    _text_shadow(frame, f"Y:{yaw:+.0f} P:{pitch:+.0f} R:{roll:+.0f}",
                 (x1 + 4, y2 - 18), 0.36, COLOR_YELLOW)


def draw_landmarks(frame: np.ndarray, landmark: np.ndarray) -> None:
    """Draw 68 facial landmarks as small cyan dots."""
    pts = landmark.reshape(68, 2).astype(int)
    for x, y in pts:
        cv2.circle(frame, (x, y), 1, COLOR_CYAN, -1)


def draw_right_panel(
    frame: np.ndarray,
    results: list,
    fps: float,
    known_count: int,
    registering: bool,
    reg_name: str,
) -> None:
    """
    Draw a semi-transparent info panel on the right side of the frame.

    *results* is the list of per-face dicts built in the main loop.
    """
    h, w = frame.shape[:2]
    px   = w - PANEL_W

    # Panel background
    overlay = frame.copy()
    cv2.rectangle(overlay, (px, 0), (w, h), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    cv2.line(frame, (px, 0), (px, h), COLOR_GRAY, 1)

    y = 22
    _text_shadow(frame, "FACE RECOGNITION", (px + 8, y), 0.48, COLOR_CYAN, 1)
    y += 18
    cv2.line(frame, (px + 6, y), (w - 6, y), COLOR_GRAY, 1)
    y += 14

    _text_shadow(frame, f"FPS: {fps:.1f}",       (px + 8, y), 0.45, COLOR_GREEN, 1)
    y += 16
    _text_shadow(frame, f"Known: {known_count}",  (px + 8, y), 0.42, COLOR_WHITE, 1)
    y += 14
    _text_shadow(frame, f"Detected: {len(results)}", (px + 8, y), 0.42, COLOR_WHITE, 1)
    y += 18
    cv2.line(frame, (px + 6, y), (w - 6, y), COLOR_GRAY, 1)
    y += 10

    for i, res in enumerate(results):
        name       = res["name"]
        similarity = res["similarity"]
        det_score  = res["det_score"]
        pose       = res["pose"]
        aligned    = res["aligned"]   # 128x128 BGR

        is_known = name != "Unknown"
        color    = COLOR_GREEN if is_known else COLOR_RED

        # Aligned-face thumbnail
        thumb = cv2.resize(aligned, (THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        ty1   = y
        ty2   = y + THUMBNAIL_SIZE
        tx1   = px + 8
        tx2   = tx1 + THUMBNAIL_SIZE
        if ty2 < h and tx2 < w:
            frame[ty1:ty2, tx1:tx2] = thumb
            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), color, 2)

        # Text beside thumbnail
        tx = tx2 + 8
        _text_shadow(frame, f"#{i + 1}",          (tx, ty1 + 12), 0.45, color,    1)
        _text_shadow(frame, name[:12],             (tx, ty1 + 26), 0.40, COLOR_WHITE, 1)
        _text_shadow(frame, f"det:{det_score:.2f}", (tx, ty1 + 40), 0.36, COLOR_CYAN, 1)
        yaw, pitch, roll = pose
        _text_shadow(frame, f"Y{yaw:+.0f}",   (tx,       ty1 + 54), 0.34, COLOR_YELLOW, 1)
        _text_shadow(frame, f"P{pitch:+.0f}", (tx + 34,  ty1 + 54), 0.34, COLOR_YELLOW, 1)
        _text_shadow(frame, f"R{roll:+.0f}",  (tx + 68,  ty1 + 54), 0.34, COLOR_YELLOW, 1)

        # Similarity bar
        bar_y = ty1 + THUMBNAIL_SIZE + 8
        if bar_y + 20 < h:
            _similarity_bar(frame, px + 8, bar_y, similarity, name)

        y = ty1 + THUMBNAIL_SIZE + 28
        cv2.line(frame, (px + 6, y), (w - 6, y), (60, 60, 60), 1)
        y += 8

        if y + THUMBNAIL_SIZE + 40 > h:
            break

    # Registration banner
    if registering:
        banner = f"[R] Register as: {reg_name}"
        cv2.rectangle(frame, (px + 4, h - 46), (w - 4, h - 6), (0, 120, 255), -1)
        cv2.putText(frame, banner, (px + 8, h - 28), FONT, 0.42, COLOR_WHITE, 1, cv2.LINE_AA)

    # Keyboard hints
    hint_y = h - 56 if registering else h - 50
    _text_shadow(frame, "Q/Esc: Quit",    (px + 8, hint_y),      0.35, COLOR_GRAY, 1)
    _text_shadow(frame, "R: Register cam", (px + 8, hint_y + 14), 0.35, COLOR_GRAY, 1)
    _text_shadow(frame, "U: Upload image", (px + 8, hint_y + 28), 0.35, (180, 140, 255), 1)


def draw_fps_badge(frame: np.ndarray, fps: float) -> None:
    """Draw a compact FPS badge in the top-left corner."""
    txt = f" FPS {fps:.1f} "
    (tw, th), _ = cv2.getTextSize(txt, FONT, 0.55, 1)
    cv2.rectangle(frame, (6, 6),  (14 + tw, 14 + th), COLOR_DARK, -1)
    cv2.rectangle(frame, (6, 6),  (14 + tw, 14 + th), COLOR_CYAN, 1)
    cv2.putText(frame, txt, (10, 10 + th), FONT, 0.55, COLOR_CYAN, 1, cv2.LINE_AA)


def draw_face_count_badge(frame: np.ndarray, n: int) -> None:
    """Draw a face count badge just below the FPS badge."""
    txt = f" Faces: {n} "
    (tw, th), _ = cv2.getTextSize(txt, FONT, 0.50, 1)
    cv2.rectangle(frame, (6, 30), (14 + tw, 40 + th), COLOR_DARK, -1)
    cv2.rectangle(frame, (6, 30), (14 + tw, 40 + th), COLOR_YELLOW, 1)
    cv2.putText(frame, txt, (10, 34 + th), FONT, 0.50, COLOR_YELLOW, 1, cv2.LINE_AA)


# ===========================================================================
# FPS tracker
# ===========================================================================
class FPSCounter:
    """Sliding-window FPS estimator."""

    def __init__(self, window: int = 30) -> None:
        self._times: deque = deque(maxlen=window)

    def tick(self) -> float:
        now = time.monotonic()
        self._times.append(now)
        if len(self._times) < 2:
            return 0.0
        return (len(self._times) - 1) / (self._times[-1] - self._times[0])


# ===========================================================================
# Main loop
# ===========================================================================
def main() -> None:
    args        = parse_args()
    known_faces = load_known_faces(args.known_dir)
    camera      = open_camera(args.camera, args.width, args.height)

    if not camera.isOpened():
        raise RuntimeError(
            f"Could not open camera {args.camera}. "
            "Check the connection or try --camera 1."
        )

    fps_counter = FPSCounter()
    fps         = 0.0

    # Live-registration state
    registering  = False
    reg_name     = ""
    reg_capture  = None   # best-scored result dict from last frame

    print("Camera started.")
    print("  Q / Esc  - quit")
    print("  R        - register the best detected face (from camera)")
    print("  U        - upload an image file to register a known person")
    print(f"  Known-face folder: {args.known_dir.resolve()}")
    if not _TK_AVAILABLE:
        print("  [WARN] tkinter not found - Upload (U) feature disabled.")

    window_name = "Open Source Face Recognition - Enhanced"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        while True:
            frame_ok, frame = camera.read()
            if not frame_ok:
                print("[WARN] Failed to read frame; retrying ...")
                time.sleep(0.05)
                continue

            fps = fps_counter.tick()

            # ------------------------------------------------------------------
            # Detection + full recognition pipeline
            # ------------------------------------------------------------------
            boxes, scores = get_face_boundingbox(frame)
            face_count    = min(len(boxes), args.max_faces)
            results       = []

            for idx in range(face_count):
                box       = boxes[idx]
                det_score = float(scores[idx].detach().cpu().item())

                try:
                    landmark, aligned_face, feature = extract_landmark_and_feature(frame, box)
                    pose = extract_pose(box, landmark)
                except Exception as exc:
                    print(f"[WARN] Feature extraction failed for face {idx}: {exc}")
                    continue

                name, similarity = recognize_face(feature, known_faces, args.threshold)
                x1, y1, x2, y2  = box.detach().cpu().numpy().astype(int)

                results.append(dict(
                    name       = name,
                    similarity = similarity,
                    det_score  = det_score,
                    pose       = pose,
                    aligned    = aligned_face,
                    landmark   = landmark,
                    bbox       = (x1, y1, x2, y2),
                    feature    = feature,
                ))

                # draw_face_box(frame, x1, y1, x2, y2,
                #               name, similarity, det_score, pose, idx)
                # draw_landmarks(frame, landmark)

            # ------------------------------------------------------------------
            # Track best face for registration
            # ------------------------------------------------------------------
            reg_capture = (
                max(results, key=lambda r: r["det_score"])
                if results else None
            )

            # ------------------------------------------------------------------
            # HUD
            # ------------------------------------------------------------------
            draw_right_panel(frame, results, fps,
                             known_count = len(known_faces),
                             registering = registering,
                             reg_name    = reg_name)
            draw_fps_badge(frame, fps)
            draw_face_count_badge(frame, face_count)

            cv2.imshow(window_name, frame)

            # ------------------------------------------------------------------
            # Key handling
            # ------------------------------------------------------------------
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):   # Q or Esc - quit
                break

            elif key == ord("r") and reg_capture is not None:
                # --- Register from live camera capture ---
                registering = True
                print("\n[REGISTER] Enter name for the detected face: ", end="", flush=True)
                reg_name = input().strip()

                if reg_name:
                    h_frame, w_frame = frame.shape[:2]
                    bx1, by1, bx2, by2 = reg_capture["bbox"]
                    bx1 = max(0, bx1);  by1 = max(0, by1)
                    bx2 = min(w_frame, bx2); by2 = min(h_frame, by2)
                    face_crop = frame[by1:by2, bx1:bx2].copy()

                    save_known_face(
                        args.known_dir.resolve(),
                        reg_name,
                        face_crop,
                        reg_capture["aligned"],
                        reg_capture["feature"],
                        known_faces,
                    )
                    print(f"[INFO] '{reg_name}' registered and added to in-memory database.")
                else:
                    print("[INFO] Registration cancelled (empty name).")

                registering = False
                reg_name    = ""

            elif key == ord("u"):
                # --- Register from uploaded image file (file dialog) ---
                print("\n[UPLOAD] Opening file picker dialog ...")
                registered = register_from_image_file(args.known_dir, known_faces)
                if registered:
                    print(f"[INFO] Upload registration complete. "
                          f"Known faces: {len(known_faces)}. "
                          f"Camera is now recognizing '{registered}'.")

    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("Camera released. Bye!")


if __name__ == "__main__":
    main()
