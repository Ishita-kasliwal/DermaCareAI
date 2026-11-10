"""tf.data input pipelines, augmentation and class weights."""

from __future__ import annotations

import hashlib
from pathlib import Path

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

from skinai_ml.preprocess import PreprocessConfig, load_and_preprocess_file, to_model_input

AUTOTUNE = tf.data.AUTOTUNE


def preprocess_config_from(cfg: dict) -> PreprocessConfig:
    p = cfg["preprocess"]
    return PreprocessConfig(image_size=int(p["image_size"]), crop=p.get("crop", "center_square"))


def build_augmenter(cfg: dict, seed: int) -> keras.Sequential | None:
    a = cfg.get("augmentation", {})
    if not a.get("enabled", True):
        return None
    layers = [keras.layers.RandomFlip(a.get("flip", "horizontal_and_vertical"), seed=seed)]
    if a.get("rotation"):
        layers.append(keras.layers.RandomRotation(a["rotation"], fill_mode="reflect", seed=seed))
    if a.get("zoom"):
        z = float(a["zoom"])
        layers.append(keras.layers.RandomZoom((-z, z), fill_mode="reflect", seed=seed))
    if a.get("contrast"):
        layers.append(keras.layers.RandomContrast(a["contrast"], seed=seed))
    if a.get("brightness"):
        layers.append(keras.layers.RandomBrightness(a["brightness"], value_range=(0, 255), seed=seed))
    return keras.Sequential(layers, name="augmentation")


def make_dataset(
    df: pd.DataFrame,
    cfg: dict,
    num_classes: int,
    training: bool,
    cache_dir: Path | None = None,
) -> tf.data.Dataset:
    pcfg = preprocess_config_from(cfg)
    seed = int(cfg["seed"])
    bs = int(cfg["training"]["batch_size"])

    paths = df["path"].astype(str).values
    labels = df["label"].astype(np.int32).values
    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    ds = ds.map(
        lambda p, y: (load_and_preprocess_file(p, pcfg), tf.one_hot(y, num_classes)),
        num_parallel_calls=AUTOTUNE,
        deterministic=True,
    )
    # cache decoded+resized uint8 images (~150 KB each at 224px) so later epochs skip JPEG decode
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(("|".join(paths) + str(pcfg.to_dict())).encode()).hexdigest()[:12]
        ds = ds.cache(str(cache_dir / f"cache_{key}"))
    else:
        ds = ds.cache()

    if training:
        ds = ds.shuffle(len(paths), seed=seed, reshuffle_each_iteration=True)
    ds = ds.batch(bs)
    ds = ds.map(lambda x, y: (to_model_input(x), y), num_parallel_calls=AUTOTUNE)
    if training:
        aug = build_augmenter(cfg, seed)
        if aug is not None:
            ds = ds.map(
                lambda x, y: (tf.clip_by_value(aug(x, training=True), 0.0, 255.0), y),
                num_parallel_calls=AUTOTUNE,
            )
    return ds.prefetch(AUTOTUNE)


def compute_class_weights(labels: np.ndarray, num_classes: int, power: float = 0.5) -> dict[int, float]:
    """Inverse-frequency weights ** power, normalised so the weighted mean over samples is 1."""
    counts = np.bincount(labels, minlength=num_classes).astype(float)
    if (counts == 0).any():
        raise ValueError(f"some classes have no training samples: {counts.tolist()}")
    w = (counts.sum() / (num_classes * counts)) ** power
    w = w / (w * counts).sum() * counts.sum()
    return {i: float(round(w[i], 6)) for i in range(num_classes)}
