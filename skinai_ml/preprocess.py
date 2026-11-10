"""Image preprocessing shared by training (tf.data) and inference (prediction.py).

Using the SAME TensorFlow ops in both places prevents train/serve skew.

Contract
--------
input : uint8 RGB tensor/array, shape (H, W, 3), any size
output: uint8 RGB tensor, shape (S, S, 3), where S = image_size
The model receives float32 values in [0, 255]. Model-specific normalisation
(MobileNetV2 -> [-1, 1]; EfficientNetB0 built-in) lives INSIDE the saved model,
so callers never need to know which architecture was chosen.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import tensorflow as tf

CROP_MODES = ("center_square", "none")


@dataclass(frozen=True)
class PreprocessConfig:
    image_size: int = 224
    crop: str = "center_square"  # center_square | none
    resize_method: str = "bilinear"
    antialias: bool = True
    channel_order: str = "RGB"
    input_dtype: str = "float32"
    input_range: tuple[int, int] = (0, 255)
    normalization: str = "inside_model"
    exif_transpose: bool = True
    version: int = 1
    notes: list[str] = field(
        default_factory=lambda: [
            "Center-crop to square (dermoscopic lesions are centred), then resize.",
            "Values rounded to uint8 after resize so cached training data == inference input.",
        ]
    )

    def __post_init__(self):
        if self.crop not in CROP_MODES:
            raise ValueError(f"crop must be one of {CROP_MODES}, got {self.crop!r}")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["input_range"] = list(self.input_range)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PreprocessConfig:
        d = dict(d)
        if "input_range" in d:
            d["input_range"] = tuple(d["input_range"])
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def preprocess_image(image, cfg: PreprocessConfig) -> tf.Tensor:
    """uint8 (H, W, 3) -> uint8 (S, S, 3). Works eagerly and inside tf.data graphs."""
    image = tf.convert_to_tensor(image)
    if image.dtype != tf.uint8:
        raise TypeError(f"expected uint8 image, got {image.dtype}")
    image = image[..., :3]

    if cfg.crop == "center_square":
        h = tf.shape(image)[0]
        w = tf.shape(image)[1]
        s = tf.minimum(h, w)
        image = tf.image.crop_to_bounding_box(image, (h - s) // 2, (w - s) // 2, s, s)

    image = tf.image.resize(
        image, [cfg.image_size, cfg.image_size], method=cfg.resize_method, antialias=cfg.antialias
    )
    image = tf.cast(tf.clip_by_value(tf.round(image), 0.0, 255.0), tf.uint8)
    image.set_shape([cfg.image_size, cfg.image_size, 3])
    return image


def load_and_preprocess_file(path: tf.Tensor, cfg: PreprocessConfig) -> tf.Tensor:
    """tf.data helper: file path -> preprocessed uint8 image."""
    raw = tf.io.read_file(path)
    img = tf.io.decode_image(raw, channels=3, expand_animations=False)
    img.set_shape([None, None, 3])
    return preprocess_image(img, cfg)


def to_model_input(batch_uint8: tf.Tensor) -> tf.Tensor:
    return tf.cast(batch_uint8, tf.float32)
