"""Reusable inference module.

Usage (library):
    from skinai_ml.prediction import SkinLesionPredictor
    predictor = SkinLesionPredictor("ml/artifacts/models/<version>")
    result = predictor.predict("lesion.jpg")      # path, bytes, file-like or PIL.Image
    print(result.to_dict())

Usage (CLI):
    python -m skinai_ml.prediction --model-dir ml/artifacts/models/<version> image.jpg

A model directory is produced by ml/src/export.py and contains:
    model.keras Â· labels.json Â· preprocess_config.json Â· manifest.json (sha256) Â· metrics.json

DISCLAIMER: outputs are model scores for 7 HAM10000 categories, not a diagnosis.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from skinai_ml.classes import CLASS_INFO
from skinai_ml.preprocess import PreprocessConfig, preprocess_image, to_model_input, tta_views

DISCLAIMER = (
    "Research/education output for 7 dermoscopic lesion categories only. "
    "Not a medical diagnosis. Consult a dermatologist."
)

MIN_SIDE_PX = 64
MAX_PIXELS = 40_000_000  # decompression-bomb guard


class ModelIntegrityError(RuntimeError):
    pass


@dataclass
class PredictionResult:
    code: str
    name: str
    risk_level: str
    confidence: float
    status: str  # "confident" | "inconclusive"
    probabilities: dict[str, float]
    top_k: list[dict[str, Any]]
    model_version: str
    threshold: float
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_rgb_image(image) -> np.ndarray:
    """Accepts a path, bytes, file-like object or PIL image; returns uint8 RGB (H, W, 3)."""
    if isinstance(image, Image.Image):
        img = image
    elif isinstance(image, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image))
    elif isinstance(image, (str, Path)):
        img = Image.open(image)
    elif hasattr(image, "read"):
        img = Image.open(image)
    else:
        raise TypeError(f"unsupported image type: {type(image)!r}")

    if img.width * img.height > MAX_PIXELS:
        raise ValueError("image too large")
    img = ImageOps.exif_transpose(img)  # respect camera orientation
    img = img.convert("RGB")
    if min(img.size) < MIN_SIDE_PX:
        raise ValueError(f"image too small (min side {MIN_SIDE_PX}px)")
    return np.asarray(img, dtype=np.uint8)


class SkinLesionPredictor:
    """Thread-safe, lazily loaded predictor for an exported model directory."""

    def __init__(
        self,
        model_dir: str | Path,
        confidence_threshold: float | None = None,
        verify_checksum: bool = True,
    ):
        self.model_dir = Path(model_dir)
        self.verify_checksum = verify_checksum
        self._lock = threading.Lock()
        self._model = None

        self.manifest = self._read_json("manifest.json")
        self.labels: list[dict] = self._read_json("labels.json")
        self.preprocess_cfg = PreprocessConfig.from_dict(self._read_json("preprocess_config.json"))
        self.class_codes = [entry["code"] for entry in sorted(self.labels, key=lambda e: e["index"])]
        self.model_version: str = self.manifest["version"]
        self.threshold = float(
            confidence_threshold
            if confidence_threshold is not None
            else self.manifest.get("confidence_threshold", 0.5)
        )

    # ------------------------------------------------------------------ loading
    def _read_json(self, name: str):
        path = self.model_dir / name
        if not path.exists():
            raise FileNotFoundError(f"{name} not found in {self.model_dir}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            import keras  # imported lazily: keeps app start fast until first use

            model_path = self.model_dir / self.manifest.get("model_file", "model.keras")
            if self.verify_checksum:
                actual = sha256_file(model_path)
                if actual != self.manifest["model_sha256"]:
                    raise ModelIntegrityError(
                        f"checksum mismatch for {model_path.name}: refusing to load"
                    )
            model = keras.models.load_model(model_path, compile=False)
            n_out = model.output_shape[-1]
            if n_out != len(self.class_codes):
                raise ModelIntegrityError(
                    f"model outputs {n_out} classes but labels.json has {len(self.class_codes)}"
                )
            self._model = model
            return model

    def warmup(self) -> None:
        s = self.preprocess_cfg.image_size
        self.predict_array(np.zeros((s, s, 3), dtype=np.uint8))

    # --------------------------------------------------------------- inference
    def predict_array(self, rgb_uint8: np.ndarray) -> PredictionResult:
        model = self._load()
        x = preprocess_image(rgb_uint8, self.preprocess_cfg)
        x = to_model_input(x)[None, ...]
        views = tta_views(x, self.preprocess_cfg.tta)  # same TTA as used in evaluation
        import tensorflow as tf

        out = np.asarray(model(tf.concat(views, axis=0), training=False))
        probs = out.mean(axis=0).astype(float)
        return self._build_result(probs)

    def predict(self, image) -> PredictionResult:
        return self.predict_array(load_rgb_image(image))

    def _build_result(self, probs: np.ndarray, k: int = 3) -> PredictionResult:
        order = np.argsort(probs)[::-1]
        top = int(order[0])
        code = self.class_codes[top]
        info = CLASS_INFO.get(code)
        conf = float(probs[top])
        return PredictionResult(
            code=code,
            name=info.name if info else code,
            risk_level=info.risk_level if info else "unknown",
            confidence=round(conf, 6),
            status="confident" if conf >= self.threshold else "inconclusive",
            probabilities={c: round(float(p), 6) for c, p in zip(self.class_codes, probs, strict=True)},
            top_k=[
                {"code": self.class_codes[i], "probability": round(float(probs[i]), 6)}
                for i in order[:k]
            ],
            model_version=self.model_version,
            threshold=self.threshold,
        )


def _main() -> None:
    ap = argparse.ArgumentParser(description="Classify a dermoscopic skin-lesion image.")
    ap.add_argument("image", nargs="+")
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()

    predictor = SkinLesionPredictor(args.model_dir, confidence_threshold=args.threshold)
    for img in args.image:
        print(json.dumps({"image": img, **predictor.predict(img).to_dict()}, indent=2))


if __name__ == "__main__":
    _main()
