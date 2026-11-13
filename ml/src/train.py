"""Two-stage transfer-learning training for one model.

    python -m ml.src.train --config ml/configs/train.yaml --model efficientnetb0

Stage 1: frozen ImageNet backbone, train the classification head.
Stage 2: unfreeze the top N backbone layers (BatchNorm stays frozen), low learning rate.
The best checkpoint by the validation monitor (macro-F1) across BOTH stages is kept.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import keras
import numpy as np
import pandas as pd

from ml.src.data_pipeline import compute_class_weights, make_dataset
from ml.src.dataset import DatasetNotFoundError, get_or_create_splits
from ml.src.models import build_model, compile_model, unfreeze_top
from ml.src.utils import environment_info, load_config, resolve, save_json, set_global_seed, timestamp


def train_model(cfg: dict, model_cfg: dict, df: pd.DataFrame, run_dir: Path) -> dict:
    set_global_seed(int(cfg["seed"]), cfg.get("deterministic", True))
    import tensorflow as tf

    if cfg.get("mixed_precision") and tf.config.list_physical_devices("GPU"):
        keras.mixed_precision.set_global_policy("mixed_float16")  # ~2x faster on modern GPUs
    run_dir.mkdir(parents=True, exist_ok=True)
    classes = cfg["data"]["classes"]
    k = len(classes)
    tcfg = cfg["training"]
    monitor = tcfg.get("monitor", "val_macro_f1")
    cache_dir = resolve(cfg["output_dir"]) / "cache"

    train_df = df[df["split"] == "train"]
    val_df = df[df["split"] == "val"]
    ds_train = make_dataset(train_df, cfg, k, training=True, cache_dir=cache_dir)
    ds_val = make_dataset(val_df, cfg, k, training=False, cache_dir=cache_dir)

    class_weight = None
    imb = cfg.get("imbalance", {"method": "none"})
    if imb.get("method") == "class_weight":
        boost = {classes.index(c): f for c, f in (imb.get("boost") or {}).items() if c in classes}
        class_weight = compute_class_weights(train_df["label"].values, k, float(imb.get("power", 0.5)), boost)

    model, backbone = build_model(
        model_cfg["name"], k, int(cfg["preprocess"]["image_size"]),
        weights=model_cfg.get("weights", "imagenet"), dropout=float(model_cfg.get("dropout", 0.3)),
    )
    best_path = run_dir / "best.keras"
    csv_log = run_dir / "history.csv"
    patience = int(tcfg.get("early_stopping_patience", 4))
    ls = float(tcfg.get("label_smoothing", 0.0))

    def callbacks(initial_best=None):
        return [
            keras.callbacks.ModelCheckpoint(
                best_path, monitor=monitor, mode="max", save_best_only=True,
                initial_value_threshold=initial_best,
            ),
            keras.callbacks.EarlyStopping(monitor=monitor, mode="max", patience=patience,
                                          restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.3, patience=2, min_lr=1e-7),
            keras.callbacks.CSVLogger(str(csv_log), append=True),
        ]

    t0 = time.time()
    # ---- stage 1
    s1 = model_cfg["stage1"]
    compile_model(model, k, float(s1["learning_rate"]), ls)
    h1 = model.fit(ds_train, validation_data=ds_val, epochs=int(s1["epochs"]),
                   class_weight=class_weight, callbacks=callbacks(), verbose=2)
    hist = {key: list(map(float, v)) for key, v in h1.history.items()}
    best_s1 = float(np.max(h1.history[monitor]))
    epochs_done = len(h1.history["loss"])

    # ---- stage 2
    s2 = model_cfg.get("stage2") or {}
    best_s2 = None
    if int(s2.get("epochs", 0)) > 0:
        n_trainable = unfreeze_top(backbone, int(s2.get("unfreeze_last", 40)))
        compile_model(model, k, float(s2["learning_rate"]), ls)
        h2 = model.fit(ds_train, validation_data=ds_val, initial_epoch=epochs_done,
                       epochs=epochs_done + int(s2["epochs"]), class_weight=class_weight,
                       callbacks=callbacks(initial_best=best_s1), verbose=2)
        for key, v in h2.history.items():
            hist.setdefault(key, []).extend(map(float, v))
        best_s2 = float(np.max(h2.history[monitor]))
        hist["stage2_trainable_backbone_layers"] = [n_trainable]

    if not best_path.exists():  # e.g. metric never improved from -inf (shouldn't happen)
        model.save(best_path)

    info = {
        "model": model_cfg["name"],
        "run_dir": str(run_dir),
        "best_checkpoint": str(best_path),
        "monitor": monitor,
        "best_stage1": best_s1,
        "best_stage2": best_s2,
        "best_val_monitor": max(v for v in (best_s1, best_s2) if v is not None),
        "class_weight": class_weight,
        "train_seconds": round(time.time() - t0, 1),
        "model_config": model_cfg,
        "environment": environment_info(),
    }
    save_json(hist, run_dir / "history.json")
    save_json(info, run_dir / "train_info.json")
    return info


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    cfg = load_config(args.config)
    model_cfg = next((m for m in cfg["models"] if m["name"] == args.model), None)
    if model_cfg is None:
        raise SystemExit(f"model {args.model!r} not in config")
    try:
        df = get_or_create_splits(cfg)
    except DatasetNotFoundError as e:
        raise SystemExit(str(e)) from None
    run_dir = resolve(cfg["output_dir"]) / "runs" / f"{args.model}-{timestamp()}"
    info = train_model(cfg, model_cfg, df, run_dir)
    print(f"best {info['monitor']}={info['best_val_monitor']:.4f}  -> {info['best_checkpoint']}")


if __name__ == "__main__":
    _main()
