"""Find where training time goes: input pipeline (decode/augment) vs model step, with/without determinism.

    python -m ml.src.profile_pipeline [--deterministic]
"""

from __future__ import annotations

import argparse
import time

import tensorflow as tf

from ml.src.data_pipeline import make_dataset
from ml.src.dataset import get_or_create_splits
from ml.src.models import build_model, compile_model
from ml.src.utils import deep_update, load_config, resolve, set_global_seed


def time_iter(ds, batches: int) -> float:
    it = iter(ds)
    next(it)  # warm-up
    t0 = time.perf_counter()
    for _ in range(batches):
        next(it)
    return (time.perf_counter() - t0) / batches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deterministic", action="store_true")
    ap.add_argument("--batches", type=int, default=15)
    args = ap.parse_args()
    cfg = load_config("ml/configs/train.yaml")
    set_global_seed(42, args.deterministic)
    df = get_or_create_splits(cfg)
    train = df[df["split"] == "train"].head(32 * (args.batches + 2))
    k = len(cfg["data"]["classes"])
    cache = resolve("ml/artifacts/cache_profile")

    # warm the file cache once so we measure steady-state epochs (what epochs 2+ look like)
    no_aug = make_dataset(train, deep_update(cfg, {"augmentation": {"enabled": False}}), k, True, cache)
    for _ in no_aug:
        pass
    with_aug = make_dataset(train, cfg, k, True, cache)

    print(f"deterministic={args.deterministic}  threads={tf.config.threading.get_inter_op_parallelism_threads()}")
    print(f"input pipeline, cached, no augmentation : {time_iter(no_aug, args.batches):.3f} s/batch")
    print(f"input pipeline, cached, with augmentation: {time_iter(with_aug, args.batches):.3f} s/batch")

    model, _ = build_model("mobilenetv2", k, 224, weights="imagenet")
    compile_model(model, k, 1e-3)
    x, y = next(iter(no_aug))
    model.train_on_batch(x, y)
    t0 = time.perf_counter()
    for _ in range(args.batches):
        model.train_on_batch(x, y)
    print(f"model step only (mobilenetv2 stage 1)   : {(time.perf_counter() - t0) / args.batches:.3f} s/batch")
    t0 = time.perf_counter()
    model.fit(with_aug.take(args.batches), epochs=1, verbose=0)
    print(f"fit() on augmented pipeline             : {(time.perf_counter() - t0) / args.batches:.3f} s/batch")


if __name__ == "__main__":
    main()
