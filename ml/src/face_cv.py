"""Honest accuracy estimate for the small face/rash dataset: 5-fold cross-validation grouped by person.

    python -m ml.src.face_cv [--backbone efficientnetb0] [--size 224]

ImageNet backbone as a frozen feature extractor (+ flipped view averaged) and a regularised logistic
regression on top: the most reliable approach for ~260 photos. Every photo is predicted exactly once by a
model that never saw that person.
"""

from __future__ import annotations

import argparse

import keras
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.src.utils import resolve, save_json
from skinai_ml.preprocess import PreprocessConfig, load_and_preprocess_file

ROOT = resolve("ml/data/raw/FACE")


def features(paths, backbone_name: str, size: int) -> np.ndarray:
    builder = {"efficientnetb0": keras.applications.EfficientNetB0,
               "efficientnetb3": keras.applications.EfficientNetB3}[backbone_name]
    net = builder(include_top=False, weights="imagenet", pooling="avg", input_shape=(size, size, 3))
    cfg = PreprocessConfig(image_size=size, crop="center_square")
    ds = tf.data.Dataset.from_tensor_slices(list(paths)).map(lambda p: tf.cast(load_and_preprocess_file(p, cfg), tf.float32)).batch(16)
    f1 = net.predict(ds, verbose=0)
    f2 = net.predict(ds.map(tf.image.flip_left_right), verbose=0)
    return (f1 + f2) / 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", default="efficientnetb0")
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--only", nargs="*", help="restrict to these classes")
    args = ap.parse_args()
    df = pd.read_csv(ROOT / "face_metadata.csv")
    if args.only:
        df = df[df["dx"].isin(args.only)].reset_index(drop=True)
    df["path"] = df["image_id"].map(lambda i: str(ROOT / "images" / f"{i}.jpg"))
    classes = sorted(df["dx"].unique())
    y = df["dx"].map({c: i for i, c in enumerate(classes)}).values
    X = features(df["path"], args.backbone, args.size)

    pred = np.zeros(len(df), dtype=int)
    proba = np.zeros((len(df), len(classes)))
    for _fold, (tr, te) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=42).split(X, y, df["lesion_id"])):
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=5000, class_weight="balanced"))
        clf.fit(X[tr], y[tr])
        proba[te] = clf.predict_proba(X[te])
        pred[te] = proba[te].argmax(1)

    acc, bal = accuracy_score(y, pred), balanced_accuracy_score(y, pred)
    print(f"{args.backbone}@{args.size}: 5-fold grouped CV accuracy {acc:.3f}, balanced accuracy {bal:.3f} (n={len(df)})")
    print(classification_report(y, pred, target_names=classes, digits=3, zero_division=0))
    cm = confusion_matrix(y, pred)
    print(pd.DataFrame(cm, index=[f"true {c}" for c in classes], columns=classes).to_string())
    conf = proba.max(1)
    for t in (0.5, 0.7):
        m = conf >= t
        print(f"when >= {t:.0%} sure: covers {m.mean():.0%} of photos, accuracy {accuracy_score(y[m], pred[m]):.3f}")
    save_json({"backbone": args.backbone, "size": args.size, "n": int(len(df)), "accuracy": acc,
               "balanced_accuracy": bal, "classes": classes, "confusion_matrix": cm.tolist()},
              resolve(f"ml/artifacts/face/cv_{args.backbone}_{args.size}.json"))


if __name__ == "__main__":
    main()
