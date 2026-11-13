"""Finish a pipeline from saved checkpoints when training was interrupted.

    python -m ml.src.finalize_runs --config ml/configs/train.yaml --runs <run_dir> [<run_dir> ...]

For each run it loads best.keras (the best validation round saved so far), evaluates it on the
validation and test splits, selects the best on VALIDATION macro-F1 (tie-break: melanoma sensitivity)
and exports it exactly like run_pipeline. Runs that were interrupted are marked as such.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import keras
import pandas as pd

from ml.src.data_pipeline import make_dataset
from ml.src.dataset import get_or_create_splits, splits_fingerprint
from ml.src.evaluate import evaluate_model
from ml.src.export import export_model
from ml.src.utils import environment_info, load_config, resolve, save_json, timestamp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    ap.add_argument("--runs", nargs="+", required=True)
    args = ap.parse_args()

    cfg = load_config(args.config)
    classes = cfg["data"]["classes"]
    k = len(classes)
    out_root = resolve(cfg["output_dir"])
    df = get_or_create_splits(cfg)
    fp = splits_fingerprint(df)
    val_df, test_df = df[df["split"] == "val"], df[df["split"] == "test"]
    monitor = cfg["training"].get("monitor", "val_macro_f1")

    results = []
    for run in args.runs:
        run_dir = resolve(run)
        name = run_dir.name.split("-")[0]
        mcfg = next(m for m in cfg["models"] if m["name"] == name)
        hist = pd.read_csv(run_dir / "history.csv")
        planned = int(mcfg["stage1"]["epochs"]) + int(mcfg.get("stage2", {}).get("epochs", 0))
        finished_normally = (run_dir / "train_info.json").exists()
        info = {
            "model": name, "run_dir": str(run_dir), "best_checkpoint": str(run_dir / "best.keras"),
            "monitor": monitor, "best_val_monitor": float(hist[monitor].max()),
            "rounds_completed": int(len(hist)), "rounds_planned": planned,
            "interrupted": not finished_normally,
            "model_config": mcfg, "environment": environment_info(),
            "note": None if finished_normally else
            f"Training was interrupted after {len(hist)} of up to {planned} rounds; the best checkpoint "
            "saved so far (by validation macro-F1) was used.",
        }
        best = keras.models.load_model(info["best_checkpoint"], compile=False)
        cache = out_root / "cache"
        val_m = evaluate_model(best, make_dataset(val_df, cfg, k, False, cache), val_df, classes, run_dir, "val", tta=cfg["preprocess"].get("tta") or ())
        test_m = evaluate_model(best, make_dataset(test_df, cfg, k, False, cache), test_df, classes, run_dir, "test", tta=cfg["preprocess"].get("tta") or ())
        mel = (val_m["per_class"].get("mel", {}).get("recall_sensitivity") or 0.0) if "mel" in classes else 0.0
        save_json(info, run_dir / "finalize_info.json")
        results.append({"model": name, "info": info, "val": val_m, "test": test_m,
                        "val_macro_f1": val_m["macro_f1"], "val_balanced_accuracy": val_m["balanced_accuracy"],
                        "val_mel_sensitivity": mel, "test_macro_f1": test_m["macro_f1"],
                        "test_balanced_accuracy": test_m["balanced_accuracy"],
                        "train_seconds": "n/a (interrupted)" if info["interrupted"] else "see run"})
        print(f"{name}: val macro-F1 {val_m['macro_f1']:.4f} | test macro-F1 {test_m['macro_f1']:.4f}, "
              f"balanced acc {test_m['balanced_accuracy']:.4f}"
              f"{'  [interrupted run]' if info['interrupted'] else ''}", flush=True)

    best = max(results, key=lambda r: (round(r["val_macro_f1"], 4), r["val_mel_sensitivity"]))
    comparison = [{k2: r[k2] for k2 in ("model", "val_macro_f1", "val_balanced_accuracy", "val_mel_sensitivity",
                                         "test_macro_f1", "test_balanced_accuracy", "train_seconds")}
                  for r in results]
    export_dir = export_model(cfg, best["info"], best["val"], best["test"], fp, comparison)
    if best["info"]["interrupted"]:
        card = Path(export_dir) / "MODEL_CARD.md"
        card.write_text(card.read_text(encoding="utf-8").replace(
            "## Limitations", f"> **Note:** {best['info']['note']}\n\n## Limitations", 1), encoding="utf-8")
    save_json({"selected": best["model"], "export_dir": str(export_dir), "splits_fingerprint": fp,
               "comparison": comparison}, out_root / "reports" / f"pipeline_finalized_{timestamp()}.json")
    print(f"selected {best['model']} -> {export_dir}")


if __name__ == "__main__":
    main()
