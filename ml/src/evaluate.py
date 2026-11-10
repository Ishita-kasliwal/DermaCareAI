"""Evaluation: precision, recall (sensitivity), specificity, F1, confusion matrix, ROC-AUC.

All values are computed from model outputs on a held-out split; nothing is hard-coded.
These are retrospective HAM10000 benchmark numbers, NOT clinical diagnostic accuracy.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)

from ml.src.utils import save_json  # noqa: E402
from skinai_ml.classes import MALIGNANT_CODES  # noqa: E402

THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _safe_div(a: float, b: float) -> float | None:
    return float(a / b) if b else None


def compute_metrics(y_true: np.ndarray, probs: np.ndarray, classes: list[str]) -> dict:
    k = len(classes)
    labels = list(range(k))
    y_pred = probs.argmax(axis=1)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    n = cm.sum()

    per_class = {}
    for i, c in enumerate(classes):
        tp = cm[i, i]
        fn = cm[i, :].sum() - tp
        fp = cm[:, i].sum() - tp
        tn = n - tp - fn - fp
        binary_true = (y_true == i).astype(int)
        auc = (roc_auc_score(binary_true, probs[:, i])
               if 0 < binary_true.sum() < len(binary_true) else None)
        prec = _safe_div(tp, tp + fp)
        rec = _safe_div(tp, tp + fn)
        per_class[c] = {
            "support": int(tp + fn),
            "precision": prec,
            "recall_sensitivity": rec,
            "specificity": _safe_div(tn, tn + fp),
            "f1": (2 * prec * rec / (prec + rec)) if prec and rec else 0.0,
            "roc_auc_ovr": None if auc is None else float(auc),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        }

    try:
        macro_auc = float(roc_auc_score(y_true, probs, multi_class="ovr", average="macro",
                                        labels=labels))
    except ValueError:
        macro_auc = None

    # malignant / pre-malignant vs benign (grouped screening view)
    mal_idx = [classes.index(c) for c in MALIGNANT_CODES if c in classes]
    t_m = np.isin(y_true, mal_idx)
    p_m = np.isin(y_pred, mal_idx)
    grouped = {
        "positive_classes": [classes[i] for i in mal_idx],
        "sensitivity": _safe_div((t_m & p_m).sum(), t_m.sum()),
        "specificity": _safe_div((~t_m & ~p_m).sum(), (~t_m).sum()),
    }

    conf = probs.max(axis=1)
    thresholds = []
    for t in THRESHOLDS:
        m = conf >= t
        thresholds.append({
            "threshold": t,
            "coverage": float(m.mean()),
            "accuracy_on_covered": float(accuracy_score(y_true[m], y_pred[m])) if m.any() else None,
            "macro_f1_on_covered": (float(f1_score(y_true[m], y_pred[m], labels=labels,
                                                   average="macro", zero_division=0))
                                    if m.any() else None),
        })

    return {
        "n_images": int(n),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=labels, average="weighted",
                                      zero_division=0)),
        "macro_roc_auc_ovr": macro_auc,
        "per_class": per_class,
        "malignant_vs_benign": grouped,
        "confidence_thresholds": thresholds,
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(
            y_true, y_pred, labels=labels, target_names=classes, output_dict=True, zero_division=0
        ),
    }


def plot_confusion(cm: np.ndarray, classes: list[str], path: Path, title: str) -> None:
    cm = np.asarray(cm)
    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax, data, ttl, fmt in ((axes[0], cm, "counts", "d"), (axes[1], norm, "row-normalised (recall)", ".2f")):
        im = ax.imshow(data, cmap="Blues")
        ax.set_xticks(range(len(classes)), classes, rotation=45)
        ax.set_yticks(range(len(classes)), classes)
        ax.set_xlabel("predicted")
        ax.set_ylabel("true")
        ax.set_title(f"{title}: {ttl}")
        for i in range(len(classes)):
            for j in range(len(classes)):
                v = data[i, j]
                ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=8,
                        color="white" if v > data.max() / 2 else "black")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def evaluate_model(model, ds, split_df: pd.DataFrame, classes: list[str], out_dir: Path,
                   split_name: str) -> dict:
    """ds must be the NON-shuffled dataset built from split_df (same order)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    probs = model.predict(ds, verbose=0)
    y_true = split_df["label"].values
    if len(probs) != len(y_true):
        raise RuntimeError("prediction count does not match split size")
    metrics = compute_metrics(y_true, probs, classes)
    metrics["split"] = split_name

    pred_df = pd.DataFrame(probs, columns=[f"p_{c}" for c in classes])
    pred_df.insert(0, "image_id", split_df["image_id"].values)
    pred_df.insert(1, "true", [classes[i] for i in y_true])
    pred_df.insert(2, "pred", [classes[i] for i in probs.argmax(1)])
    pred_df.to_csv(out_dir / f"predictions_{split_name}.csv", index=False)

    save_json(metrics, out_dir / f"metrics_{split_name}.json")
    plot_confusion(np.array(metrics["confusion_matrix"]), classes,
                   out_dir / f"confusion_matrix_{split_name}.png", split_name)
    return metrics


def metrics_markdown(metrics: dict, classes: list[str], title: str) -> str:
    def f(v):
        return "n/a" if v is None else f"{v:.3f}"

    lines = [f"### {title}", "",
             f"Images: {metrics['n_images']} · accuracy {f(metrics['accuracy'])} · "
             f"balanced accuracy {f(metrics['balanced_accuracy'])} · macro-F1 {f(metrics['macro_f1'])} · "
             f"macro ROC-AUC {f(metrics['macro_roc_auc_ovr'])}", "",
             "| class | support | precision | sensitivity (recall) | specificity | F1 | AUC |",
             "|---|---|---|---|---|---|---|"]
    for c in classes:
        p = metrics["per_class"][c]
        lines.append(f"| {c} | {p['support']} | {f(p['precision'])} | {f(p['recall_sensitivity'])} | "
                     f"{f(p['specificity'])} | {f(p['f1'])} | {f(p['roc_auc_ovr'])} |")
    g = metrics["malignant_vs_benign"]
    lines += ["", f"Malignant/pre-malignant ({', '.join(g['positive_classes'])}) vs benign: "
                  f"sensitivity {f(g['sensitivity'])}, specificity {f(g['specificity'])}"]
    return "\n".join(lines)
