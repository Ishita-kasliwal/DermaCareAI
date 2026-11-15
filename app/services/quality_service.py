"""Photo quality checks with OpenCV. Warnings are advisory; only clearly unusable images are rejected."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

ANALYSIS_SIDE = 512  # normalise size so scores are comparable across resolutions

BLUR_MIN = 40.0          # variance of Laplacian on the normalised image
DARK_MAX = 45.0          # mean brightness (0-255)
BRIGHT_MIN = 225.0
LOW_CONTRAST = 18.0      # std-dev of grey levels
BLANK_CONTRAST = 4.0     # practically uniform image -> reject
GREY_CHROMA = 4.0        # mean |R-G|+|G-B| below this -> greyscale image


@dataclass
class QualityReport:
    blur_score: float
    brightness: float
    contrast: float
    is_greyscale: bool
    issues: list[dict] = field(default_factory=list)  # {"code", "message", "severity"}

    @property
    def ok(self) -> bool:
        return not any(i["severity"] in ("warning", "error") for i in self.issues)

    @property
    def rejected(self) -> bool:
        return any(i["severity"] == "error" for i in self.issues)


_FACE_MODEL = Path(__file__).resolve().parents[1] / "assets" / "face_detection_yunet_2023mar.onnx"
_face_lock = threading.Lock()
_face_detector = None


def detect_face(rgb: np.ndarray) -> bool:
    """True if a human face is visible (OpenCV YuNet). Used to warn when a face photo is sent to the mole
    checker. Returns False if the detector isn't available, so it never blocks an upload."""
    global _face_detector
    try:
        with _face_lock:
            if _face_detector is None:
                if not _FACE_MODEL.exists():
                    return False
                _face_detector = cv2.FaceDetectorYN.create(str(_FACE_MODEL), "", (320, 320), 0.8)
            h, w = rgb.shape[:2]
            s = 640 / max(h, w)
            img = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s))))[:, :, ::-1].copy()
            _face_detector.setInputSize((img.shape[1], img.shape[0]))
            _, faces = _face_detector.detect(img)
        return faces is not None and len(faces) > 0
    except Exception:  # noqa: BLE001 - optional helper; never break uploads
        return False


def assess(rgb: np.ndarray) -> QualityReport:
    h, w = rgb.shape[:2]
    scale = ANALYSIS_SIDE / max(h, w)
    if scale < 1:
        rgb = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    blur = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    brightness = float(grey.mean())
    contrast = float(grey.std())
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    chroma = float((np.abs(r - g) + np.abs(g - b)).mean())
    report = QualityReport(round(blur, 2), round(brightness, 2), round(contrast, 2), chroma < GREY_CHROMA)

    def add(code, message, severity):
        report.issues.append({"code": code, "message": message, "severity": severity})

    if detect_face(rgb):
        add("face", "this looks like a photo of a face. The mole checker needs a close-up of ONE spot, so it can "
                    "give wrong answers on face photos. For acne, redness or rashes, use the rash checker.",
            "warning")
    if contrast < BLANK_CONTRAST:
        add("blank", "This photo looks almost blank, as if the camera was covered. "
                     "Please take a photo of the skin spot itself.", "error")
        return report
    if blur < BLUR_MIN:
        add("blurry", "the photo looks a bit blurry. Hold the camera still and tap the spot to focus.",
            "warning")
    if brightness < DARK_MAX:
        add("dark", "the photo is quite dark. Try soft daylight without shadows.", "warning")
    elif brightness > BRIGHT_MIN:
        add("overexposed", "the photo is very bright. Avoid flash and glare.", "warning")
    if contrast < LOW_CONTRAST:
        add("low_contrast", "it's hard to tell the spot apart from the skin around it.", "warning")
    if report.is_greyscale:
        add("greyscale", "this is a black-and-white photo. The AI learned from colour photos, "
                         "so the result may not be reliable.", "warning")
    return report
