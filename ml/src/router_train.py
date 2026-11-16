"""Photo sorter for "Not sure? Let the AI choose": is this a mole/spot close-up or a rash/acne/skin photo?

    python -m ml.src.router_train [--probe photo.jpg ...]

Why: in "not sure" mode both checkers used to answer, so an acne photo could show "acne" from the rash checker
next to "skin cancer" from the mole checker. Now the sorter picks ONE checker and only its answer is shown.

How: the same CLIP image features the rash checker already computes (no extra model in memory), and a
regularised logistic regression trained on
- mole-checker photos: a stratified sample of HAM10000 (all 7 types, one photo per lesion);
- rash-checker photos: every photo the rash checker was trained on (ml/src/rash_clip_train.py).
Honest estimate: 5-fold cross-validation grouped by lesion/case. The result is written as router.json (weights
folded into one linear layer) into the active rash model's folder, where the app picks it up.

Limitation: HAM10000 photos are taken with a dermatoscope, so the sorter has seen few ordinary phone photos of
moles. To stay on the safe side the app still offers the mole checker for "dark spots" answers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

from ml.src import rash_clip_train as K
from ml.src.utils import resolve

HAM = resolve("ml/data/raw/HAM10000")
N_HAM = 800
C = 0.05


def ham_sample(seed: int = 42) -> pd.DataFrame:
    meta = pd.read_csv(HAM / "HAM10000_metadata.csv")
    meta = meta.drop_duplicates("lesion_id")                       # one photo per lesion
    per = max(1, N_HAM // meta["dx"].nunique())
    rows = (meta.groupby("dx", group_keys=False)
            .apply(lambda g: g.sample(min(len(g), per), random_state=seed)))
    paths = []
    for iid in rows["image_id"]:
        for part in ("HAM10000_images_part_1", "HAM10000_images_part_2"):
            p = HAM / part / f"{iid}.jpg"
            if p.exists():
                paths.append(str(p))
                break
        else:
            paths.append(None)
    rows = rows.assign(path=paths).dropna(subset=["path"])
    return pd.DataFrame({"path": rows["path"], "group": "h_" + rows["lesion_id"], "y": 1})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", nargs="*", default=[])
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args()

    bb, emb = K.clip_parts()
    rash, F_rash = K.build_table(bb, emb)
    mole = ham_sample()
    F_mole = K.cached_embed(emb, list(mole["path"]))
    X = np.vstack([F_rash, F_mole]).astype("float32")
    y = np.concatenate([np.zeros(len(rash), int), np.ones(len(mole), int)])
    groups = np.concatenate([rash["group"].values, mole["group"].values])
    print(f"rash photos {len(rash)}, mole photos {len(mole)}")

    p = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=42).split(X, y, groups):
        sc = StandardScaler().fit(X[tr])
        lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X[tr]), y[tr])
        p[te] = lr.predict_proba(sc.transform(X[te]))[:, 1]
    pred = (p >= 0.5).astype(int)
    acc = accuracy_score(y, pred)
    cm = confusion_matrix(y, pred)
    print(f"cross-validated accuracy {acc:.3f}")
    print(pd.DataFrame(cm, index=["true rash", "true mole"], columns=["-> rash", "-> mole"]).to_string())
    by_dx = rash.assign(wrong=pred[: len(rash)] == 1).groupby("dx")["wrong"].mean()
    print("rash photos sent to the mole checker, per condition:", by_dx.round(3).to_dict())

    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X), y)
    w = (lr.coef_[0] / sc.scale_).astype(float)
    b = float(lr.intercept_[0] - (lr.coef_[0] * sc.mean_ / sc.scale_).sum())
    if not args.no_export:
        folder = resolve("ml/artifacts/face/models") / (resolve("ml/artifacts/face/models") / "LATEST").read_text().strip()
        (folder / "router.json").write_text(json.dumps({
            "what": "p(mole/spot close-up) = sigmoid(embedding . w + b); embedding = input of layer condition_probs",
            "w": w.tolist(), "b": b, "threshold": 0.5,
            "cv_accuracy": acc, "confusion": cm.tolist(), "n_rash": len(rash), "n_mole": len(mole),
        }), encoding="utf-8")
        print(f"wrote {folder / 'router.json'}")

    args.probe = [p for p in args.probe if Path(p).exists()]
    if args.probe:
        P = K.embed(emb, args.probe)
        for path, z in zip(args.probe, P @ w + b, strict=True):
            print(f"probe ...{path[-28:]}: mole-photo probability {1 / (1 + np.exp(-z)):.2f}")

if __name__ == "__main__":
    main()
