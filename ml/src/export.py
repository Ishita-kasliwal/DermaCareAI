"""Export the selected model as a self-describing, checksummed artifact directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from ml.src.data_pipeline import preprocess_config_from
from ml.src.evaluate import metrics_markdown
from ml.src.utils import config_hash, resolve, save_json, sha256_file
from skinai_ml.classes import CLASS_INFO

DATASETS = {
    "lesion": {
        "name": "HAM10000",
        "doi": "10.7910/DVN/DBW86T",
        "paper": "Tschandl, Rosendahl & Kittler, Sci Data 5, 180161 (2018), doi:10.1038/sdata.2018.161",
        "license": "CC BY-NC 4.0",
        "attribution": "(c) by ViDIR Group, Department of Dermatology, Medical University of Vienna",
    },
    "general": {
        "name": "SCIN (Skin Condition Image Network)",
        "source": "https://github.com/google-research-datasets/scin",
        "paper": "Ward et al., Creating an Empirical Dermatology Dataset Through Crowdsourcing With "
                 "Web Search Advertisements, JAMA Netw Open (2024), arXiv:2402.18545",
        "license": "SCIN Data Use License (re-identification of contributors prohibited)",
        "attribution": "SCIN dataset, Google Research and Stanford Medicine",
    },
}
DATASET_INFO = DATASETS["lesion"]  # backwards compatibility

LIMITATIONS = {
    "lesion": [
        "Dermoscopic images only; smartphone photos are out of distribution.",
        "Trained mostly on lighter skin types (Austria/Australia); performance on darker skin is unknown.",
        "Closed set of 7 classes; other conditions are forced into one of them.",
        "HAM10000 lacks patient IDs; lesion-level grouping cannot exclude same-patient overlap.",
    ],
    "general": [
        "Everyday smartphone photos from US internet users (2023); other populations are under-represented.",
        "Labels come from dermatologist panels that often disagreed; only cases where one condition held "
        ">= 50% of the panel's weight were used.",
        "Closed set of 10 condition groups; many skin conditions are not covered and will be forced into one.",
        "Small classes (about 50-100 cases); per-class test metrics rest on very few cases.",
    ],
}


def export_model(cfg: dict, train_info: dict, val_metrics: dict, test_metrics: dict,
                 splits_fingerprint: str, comparison: list[dict] | None = None) -> Path:
    classes = cfg["data"]["classes"]
    run_name = Path(train_info["run_dir"]).name  # e.g. efficientnetb0-20261110-153000
    out = resolve(cfg["output_dir"]) / "models" / run_name
    out.mkdir(parents=True, exist_ok=True)

    model_file = out / "model.keras"
    shutil.copy2(train_info["best_checkpoint"], model_file)

    labels = [{"index": i, "code": c, "name": CLASS_INFO[c].name,
               "risk_level": CLASS_INFO[c].risk_level} for i, c in enumerate(classes)]
    save_json(labels, out / "labels.json")
    save_json(preprocess_config_from(cfg).to_dict(), out / "preprocess_config.json")
    save_json({"validation": val_metrics, "test": test_metrics}, out / "metrics.json")

    domain = cfg.get("domain", "lesion")
    manifest = {
        "version": run_name,
        "domain": domain,
        "architecture": train_info["model"],
        "model_file": model_file.name,
        "model_sha256": sha256_file(model_file),
        "num_classes": len(classes),
        "classes": classes,
        "image_size": int(cfg["preprocess"]["image_size"]),
        "confidence_threshold": float(cfg.get("inference", {}).get("confidence_threshold", 0.5)),
        "selection_metric": train_info["monitor"],
        "selection_value_val": train_info["best_val_monitor"],
        "config_hash": config_hash(cfg),
        "config": cfg,
        "splits_fingerprint": splits_fingerprint,
        "group_column": cfg["data"].get("group_column", "lesion_id"),
        "dataset": DATASETS.get(domain, DATASET_INFO),
        "environment": train_info["environment"],
        "intended_use": "Research/education, non-commercial. Not a medical device.",
    }
    save_json(manifest, out / "manifest.json")
    (out / "MODEL_CARD.md").write_text(_model_card(manifest, val_metrics, test_metrics, classes,
                                                   comparison), encoding="utf-8")
    (resolve(cfg["output_dir"]) / "models" / "LATEST").write_text(run_name, encoding="utf-8")
    return out


def _model_card(m: dict, val: dict, test: dict, classes: list[str], comparison) -> str:
    parts = [
        f"# Model card: {m['version']}", "",
        f"- Architecture: **{m['architecture']}** (ImageNet transfer learning), input {m['image_size']}px",
        f"- Classes ({m['num_classes']}): {', '.join(classes)}",
        f"- Data: {m['dataset']['name']} ({m['dataset']['license']}); {m['dataset']['attribution']}",
        f"- Split: stratified, grouped by `{m['group_column']}` (no group in >1 split); "
        f"fingerprint `{m['splits_fingerprint']}`",
        f"- Selected on **validation** {m['selection_metric']} = {m['selection_value_val']:.4f}. "
        "The test split was not used for any selection.",
        f"- Inconclusive threshold: {m['confidence_threshold']}",
        f"- Environment: TF {m['environment']['tensorflow']}, Python {m['environment']['python']}",
        "",
        "## Limitations",
        *[f"- {line}" for line in LIMITATIONS.get(m.get("domain", "lesion"), LIMITATIONS["lesion"])],
        f"- **Metrics below are retrospective benchmark results on held-out {m['dataset']['name']} cases. "
        "They are not clinical diagnostic accuracy. Not a medical device.**",
        "",
        "## Results",
        metrics_markdown(val, classes, "Validation"),
        "",
        metrics_markdown(test, classes, "Test (held out, reported once)"),
    ]
    if comparison:
        parts += ["", "## Model comparison (selection on validation)", "",
                  "| model | val macro-F1 | val balanced acc | test macro-F1 | test balanced acc | train time (s) |",
                  "|---|---|---|---|---|---|"]
        for r in comparison:
            parts.append(f"| {r['model']} | {r['val_macro_f1']:.4f} | {r['val_balanced_accuracy']:.4f} | "
                         f"{r['test_macro_f1']:.4f} | {r['test_balanced_accuracy']:.4f} | {r['train_seconds']} |")
    return "\n".join(parts) + "\n"
