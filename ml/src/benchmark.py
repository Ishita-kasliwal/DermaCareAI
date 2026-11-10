"""Measure CPU training speed (seconds per batch) for each model, to estimate total training time.

    python -m ml.src.benchmark --config ml/configs/train.yaml

Uses random tensors only for TIMING; no metrics are produced.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from ml.src.data_pipeline import compute_class_weights  # noqa: F401  (import check)
from ml.src.models import build_model, compile_model, unfreeze_top
from ml.src.utils import load_config


def time_steps(model, x, y, steps: int = 6) -> float:
    model.train_on_batch(x, y)  # warm-up (graph build)
    t0 = time.perf_counter()
    for _ in range(steps):
        model.train_on_batch(x, y)
    return (time.perf_counter() - t0) / steps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    k = len(cfg["data"]["classes"])
    s = int(cfg["preprocess"]["image_size"])
    bs = int(cfg["training"]["batch_size"])
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 255, (bs, s, s, 3)).astype("float32")
    y = np.eye(k, dtype="float32")[rng.integers(0, k, bs)]

    for m in cfg["models"]:
        model, backbone = build_model(m["name"], k, s, weights=m.get("weights", "imagenet"))
        compile_model(model, k, 1e-3)
        frozen = time_steps(model, x, y)
        unfreeze_top(backbone, int(m["stage2"].get("unfreeze_last", 40)))
        compile_model(model, k, 1e-5)
        tuned = time_steps(model, x, y)
        t0 = time.perf_counter()
        model.predict(x, verbose=0)
        infer = (time.perf_counter() - t0) / bs
        print(f"{m['name']}: stage1 {frozen:.2f}s/batch, stage2 {tuned:.2f}s/batch, "
              f"inference {infer * 1000:.0f} ms/image (batch {bs}, {s}px)")


if __name__ == "__main__":
    main()
