"""Mole checker v2 experiment: CLIP image features + logistic regression on lab-confirmed HAM10000 photos.

    python -m ml.src.mole_clip_train [--all]      # --all: use every photo, not only biopsy-confirmed ones

Why: the current mole checker (EfficientNetB0) reaches 55.4% balanced accuracy on its test set. The CLIP
features that lifted the rash checker may do better. Training uses only photos whose diagnosis was confirmed by
a lab test (dx_type == "histo"), the most reliable labels in HAM10000.

Honest estimate: 5-fold cross-validation grouped by lesion (photos of the same mole never on both sides).
Reports overall accuracy, balanced accuracy (each of the 7 types counts equally), per-type recall, and
the important one: how many melanomas / skin cancers it catches.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

from ml.src import rash_clip_train as K
from ml.src.utils import resolve

HAM = resolve("ml/data/raw/HAM10000")
CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
MALIGNANT = ["akiec", "bcc", "mel"]


def table(only_histo: bool) -> pd.DataFrame:
    meta = pd.read_csv(HAM / "HAM10000_metadata.csv")
    if only_histo:
        meta = meta[meta["dx_type"] == "histo"]
    paths = {}
    for part in ("HAM10000_images_part_1", "HAM10000_images_part_2"):
        for f in (HAM / part).glob("*.jpg"):
            paths[f.stem] = str(f)
    meta = meta[meta["image_id"].isin(paths)].copy()
    meta["path"] = meta["image_id"].map(paths)
    return meta.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="use all photos, not only lab-confirmed ones")
    ap.add_argument("--C", type=float, default=0.5)
    args = ap.parse_args()

    df = table(only_histo=not args.all)
    print(df["dx"].value_counts().to_dict(), flush=True)
    _, emb = K.clip_parts()
    F = K.cached_embed(emb, list(df["path"]))
    y = df["dx"].map({c: i for i, c in enumerate(CLASSES)}).values

    proba = np.zeros((len(df), len(CLASSES)))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=42).split(F, y, df["lesion_id"]):
        sc = StandardScaler().fit(F[tr])
        lr = LogisticRegression(C=args.C, max_iter=5000, class_weight="balanced").fit(sc.transform(F[tr]), y[tr])
        proba[te] = lr.predict_proba(sc.transform(F[te]))
    pred = proba.argmax(1)
    mal = np.isin(y, [CLASSES.index(c) for c in MALIGNANT])
    mal_pred = np.isin(pred, [CLASSES.index(c) for c in MALIGNANT])
    sure = proba.max(1) >= 0.5
    out = {
        "photos": int(len(df)), "only_lab_confirmed": not args.all, "C": args.C,
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 3),
        "recall": {c: round(float((pred[y == i] == i).mean()), 3) for i, c in enumerate(CLASSES)},
        "cancer_or_precancer_caught": round(float(mal_pred[mal].mean()), 3),
        "harmless_called_harmless": round(float((~mal_pred[~mal]).mean()), 3),
        "when_at_least_50pct_sure": {"share": round(float(sure.mean()), 3),
                                     "accuracy": round(float(accuracy_score(y[sure], pred[sure])), 3)},
    }
    print(json.dumps(out, indent=2))
    print(pd.DataFrame(confusion_matrix(y, pred), index=CLASSES, columns=CLASSES).to_string())


if __name__ == "__main__":
    main()
