"""End-to-end reproducible pipeline: EDA -> grouped split -> train each model -> evaluate ->
select best on VALIDATION -> report test once -> export.

    python -m ml.src.run_pipeline --config ml/configs/train.yaml
    python -m ml.src.run_pipeline --config ml/configs/train.yaml --models efficientnetb0
"""

from __future__ import annotations

import argparse

import keras

from ml.src.data_pipeline import make_dataset
from ml.src.dataset import DatasetNotFoundError, get_or_create_splits, splits_fingerprint
from ml.src.eda import run_eda
from ml.src.evaluate import evaluate_model
from ml.src.export import export_model
from ml.src.train import train_model
from ml.src.utils import deep_update, load_config, resolve, save_json, timestamp


def run(cfg: dict, model_names: list[str] | None = None, skip_eda: bool = False) -> dict:
    classes = cfg["data"]["classes"]
    k = len(classes)
    out_root = resolve(cfg["output_dir"])
    cache_dir = out_root / "cache"

    if not skip_eda:
        run_eda(cfg)
    df = get_or_create_splits(cfg)
    fp = splits_fingerprint(df)
    val_df = df[df["split"] == "val"]
    test_df = df[df["split"] == "test"]

    models = [m for m in cfg["models"] if not model_names or m["name"] in model_names]
    if not models:
        raise SystemExit("no models selected")

    stamp = timestamp()
    results = []
    for mcfg in models:
        run_dir = out_root / "runs" / f"{mcfg['name']}-{stamp}"
        info = train_model(cfg, mcfg, df, run_dir)
        best = keras.models.load_model(info["best_checkpoint"], compile=False)
        ds_val = make_dataset(val_df, cfg, k, training=False, cache_dir=cache_dir)
        ds_test = make_dataset(test_df, cfg, k, training=False, cache_dir=cache_dir)
        val_m = evaluate_model(best, ds_val, val_df, classes, run_dir, "val", tta=cfg["preprocess"].get("tta") or ())
        test_m = evaluate_model(best, ds_test, test_df, classes, run_dir, "test", tta=cfg["preprocess"].get("tta") or ())
        mel = classes.index("mel") if "mel" in classes else None
        results.append({
            "model": mcfg["name"], "info": info, "val": val_m, "test": test_m,
            "val_macro_f1": val_m["macro_f1"], "val_balanced_accuracy": val_m["balanced_accuracy"],
            "val_mel_sensitivity": (val_m["per_class"]["mel"]["recall_sensitivity"] or 0.0)
            if mel is not None else 0.0,
            "test_macro_f1": test_m["macro_f1"], "test_balanced_accuracy": test_m["balanced_accuracy"],
            "train_seconds": info["train_seconds"],
        })

    # selection uses validation only (macro-F1, tie-break melanoma sensitivity)
    best = max(results, key=lambda r: (round(r["val_macro_f1"], 4), r["val_mel_sensitivity"]))
    comparison = [{k2: r[k2] for k2 in ("model", "val_macro_f1", "val_balanced_accuracy",
                                         "val_mel_sensitivity", "test_macro_f1",
                                         "test_balanced_accuracy", "train_seconds")} for r in results]
    export_dir = export_model(cfg, best["info"], best["val"], best["test"], fp, comparison)
    summary = {"selected": best["model"], "export_dir": str(export_dir), "splits_fingerprint": fp,
               "comparison": comparison}
    save_json(summary, out_root / "reports" / f"pipeline_{stamp}.json")
    return summary


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    ap.add_argument("--override", help="YAML file whose keys override the main config")
    ap.add_argument("--models", nargs="*", help="subset of model names to train")
    ap.add_argument("--skip-eda", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.override:
        cfg = deep_update(cfg, load_config(args.override))
    try:
        summary = run(cfg, args.models, args.skip_eda)
    except DatasetNotFoundError as e:
        raise SystemExit(str(e)) from None
    import json

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    _main()
