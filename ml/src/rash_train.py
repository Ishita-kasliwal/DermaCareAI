"""Rash checker v2: acne, skin irritation (dermatitis), eczema, ringworm + an "unfamiliar photo" check.

    python -m ml.src.rash_train --cv-only     # honest 5-fold estimate, no export
    python -m ml.src.rash_train               # estimate + export the model for the app

Data
- The supplied rash/acne photos (ml/data/raw/FACE, see face_prepare.py): acne, dermatitis, eczema, ringworm.
- SCIN (Google Research) photos already prepared by scin_prepare.py, mapped to the same four conditions
  (acne -> acne, contact_dermatitis -> dermatitis, eczema -> eczema, fungal -> ringworm), capped per class
  so SCIN does not drown out the supplied photos.

Method: frozen ImageNet EfficientNetB3 features (300 px, original + flipped view averaged) and a
regularised logistic regression, folded into one Dense softmax layer (same as face_train.py).

"Unfamiliar photo" check: for each photo we measure how close it is to the most similar training photos
(cosine similarity in feature space, mean of the 5 nearest). The cut-off is set during cross-validation so
that about 97% of genuine rash/acne photos pass. Photos below it (a selfie, a wall, clear skin) get
"this doesn't look like a skin problem the AI knows" instead of a forced answer. The training features are
saved next to the model (reference_features.npy, ~3 MB) and the cut-off in ood.json.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

from ml.src.utils import resolve

FACE = resolve("ml/data/raw/FACE")
SCIN = resolve("ml/data/raw/SCIN")
CACHE = resolve("ml/data/processed/cache")
CLASSES = ["acne", "dermatitis", "eczema", "ringworm"]
SCIN_MAP = {"acne": "acne", "contact_dermatitis": "dermatitis", "eczema": "eczema", "fungal": "ringworm"}
SCIN_CAP = 170          # max SCIN photos per condition
BACKBONE, SIZE, C = "efficientnetb3", 300, 0.05
THRESHOLD = 0.60        # "sure" cut-off for the 4-way answer
KNN = 5
OOD_KEEP = 0.97         # share of genuine photos that must pass the familiarity check


def build_table(seed: int = 42) -> pd.DataFrame:
    f = pd.read_csv(FACE / "face_metadata.csv", dtype={"image_id": str, "lesion_id": str})
    f = f[f["dx"].isin(CLASSES)].copy()
    f["path"] = f["image_id"].map(lambda i: str(FACE / "images" / f"{i}.jpg"))
    f["source"] = "supplied"
    f["group"] = "s_" + f["lesion_id"]

    s = pd.read_csv(SCIN / "scin_metadata.csv", dtype={"image_id": str, "lesion_id": str})
    s = s[s["dx"].isin(SCIN_MAP)].copy()
    s["dx"] = s["dx"].map(SCIN_MAP)
    s["path"] = s["image_id"].map(lambda i: str(SCIN / "images" / f"{i}.png"))
    s = s[s["path"].map(lambda p: __import__("os").path.exists(p))]
    # cap per class by whole cases (all photos of a case stay together)
    rng = np.random.default_rng(seed)
    keep = []
    for _dx, g in s.groupby("dx"):
        cases = g["lesion_id"].unique()
        rng.shuffle(cases)
        n = 0
        for c in cases:
            rows = g[g["lesion_id"] == c]
            if n + len(rows) > SCIN_CAP:
                continue
            keep.append(rows)
            n += len(rows)
    s = pd.concat(keep)
    s["source"] = "scin"
    s["group"] = "c_" + s["lesion_id"]
    cols = ["path", "dx", "source", "group"]
    return pd.concat([f[cols], s[cols]], ignore_index=True)


def cached_features(df: pd.DataFrame) -> np.ndarray:
    """EfficientNetB3 features, cached per image path so re-runs are fast."""
    from ml.src.face_cv import features

    CACHE.mkdir(parents=True, exist_ok=True)
    store = CACHE / f"feat_{BACKBONE}_{SIZE}.npz"
    known: dict[str, np.ndarray] = {}
    if store.exists():
        z = np.load(store, allow_pickle=False)
        known = dict(zip(z["paths"].tolist(), z["feats"], strict=True))
    todo = [p for p in df["path"] if p not in known]
    if todo:
        print(f"extracting features for {len(todo)} photos ...", flush=True)
        new = features(todo, BACKBONE, SIZE)
        known.update(zip(todo, new, strict=True))
        np.savez(store, paths=np.array(list(known)), feats=np.stack(list(known.values())))
    return np.stack([known[p] for p in df["path"]]).astype("float32")


def familiarity(train_f: np.ndarray, query_f: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    """Mean cosine similarity of each query to its KNN nearest training photos (L2-normalised features)."""
    a = train_f / np.linalg.norm(train_f, axis=1, keepdims=True)
    b = query_f / np.linalg.norm(query_f, axis=1, keepdims=True)
    sim = b @ a.T
    if exclude_self:
        np.fill_diagonal(sim, -1)
    k = min(KNN, sim.shape[1])
    return np.sort(sim, axis=1)[:, -k:].mean(1)


def fit(X, y):
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X), y)
    return sc, lr


def cross_validate(df, X, y):
    proba = np.zeros((len(df), len(CLASSES)))
    fam = np.zeros(len(df))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=42).split(X, y, df["group"]):
        sc, lr = fit(X[tr], y[tr])
        proba[te] = lr.predict_proba(sc.transform(X[te]))
        fam[te] = familiarity(X[tr], X[te])
    return proba, fam


def report(df, y, proba, fam, cut):
    pred = proba.argmax(1)
    print(f"\nall photos (n={len(df)}): accuracy {accuracy_score(y, pred):.3f}, "
          f"balanced {balanced_accuracy_score(y, pred):.3f}")
    for src in ("supplied", "scin"):
        m = (df["source"] == src).values
        print(f"  {src:9s} n={m.sum():4d}: accuracy {accuracy_score(y[m], pred[m]):.3f}, "
              f"balanced {balanced_accuracy_score(y[m], pred[m]):.3f}")
    print(classification_report(y, pred, target_names=CLASSES, digits=3, zero_division=0))
    print(pd.DataFrame(confusion_matrix(y, pred), index=[f"true {c}" for c in CLASSES], columns=CLASSES).to_string())
    conf = proba.max(1)
    for t in (0.5, THRESHOLD, 0.7):
        m = conf >= t
        print(f"when >= {t:.0%} sure: covers {m.mean():.0%}, accuracy {accuracy_score(y[m], pred[m]):.3f}")
    print(f"familiarity cut-off {cut:.4f}: genuine photos passing {(fam >= cut).mean():.1%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv-only", action="store_true")
    ap.add_argument("--probe", nargs="*", default=[], help="extra photos to score (e.g. selfies)")
    args = ap.parse_args()

    df = build_table()
    print(df.groupby(["dx", "source"]).size().unstack(fill_value=0).to_string())
    X = cached_features(df)
    y = df["dx"].map({c: i for i, c in enumerate(CLASSES)}).values
    proba, fam = cross_validate(df, X, y)
    cut = float(np.quantile(fam, 1 - OOD_KEEP))
    report(df, y, proba, fam, cut)

    if args.probe:
        from ml.src.face_cv import features

        Pf = features(args.probe, BACKBONE, SIZE)
        sc, lr = fit(X, y)
        pp = lr.predict_proba(sc.transform(Pf))
        pf = familiarity(X, Pf)
        for p, row, f in zip(args.probe, pp, pf, strict=True):
            top = ", ".join(f"{CLASSES[i]} {row[i]:.2f}" for i in row.argsort()[::-1][:2])
            print(f"probe {p[-40:]}: familiarity {f:.4f} ({'OK' if f >= cut else 'UNFAMILIAR'}) | {top}")

    if args.cv_only:
        return
    export(df, X, y, proba, fam, cut)


def export(df, X, y, proba, fam, cut) -> None:
    import keras
    import tensorflow as tf

    from ml.src.evaluate import compute_metrics, metrics_markdown, plot_confusion
    from ml.src.utils import config_hash, environment_info, save_json, sha256_file, timestamp
    from skinai_ml.classes import CLASS_INFO
    from skinai_ml.preprocess import PreprocessConfig, load_and_preprocess_file

    cv = compute_metrics(y, proba, CLASSES)
    cv["split"] = "5-fold grouped cross-validation"
    sup = (df["source"] == "supplied").values
    cv["supplied_photos_accuracy"] = float(accuracy_score(y[sup], proba[sup].argmax(1)))
    cv["familiarity_pass_rate"] = float((fam >= cut).mean())

    sc, lr = fit(X, y)
    W = (lr.coef_ / sc.scale_).T.astype("float32")
    b = (lr.intercept_ - (lr.coef_ * sc.mean_ / sc.scale_).sum(1)).astype("float32")
    inputs = keras.Input((SIZE, SIZE, 3), dtype="float32", name="image")
    backbone = keras.applications.EfficientNetB3(include_top=False, weights="imagenet", pooling="avg",
                                                 input_shape=(SIZE, SIZE, 3))
    x = backbone(inputs, training=False)
    dense = keras.layers.Dense(len(CLASSES), activation="softmax", dtype="float32", name="probs")
    model = keras.Model(inputs, dense(x), name="rash_checker_v2_effb3")
    dense.set_weights([W, b])

    cfg = PreprocessConfig(image_size=SIZE, crop="center_square")
    batch = tf.stack([tf.cast(load_and_preprocess_file(p, cfg), tf.float32) for p in df["path"][:6]])
    assert np.allclose(np.asarray(model(batch)), lr.predict_proba(sc.transform(np.asarray(backbone(batch)))),
                       atol=1e-4), "folded Keras model does not match sklearn"

    version = f"rashcheck-v2-effb3-{timestamp()}"
    out = resolve("ml/artifacts/face/models") / version
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    np.save(out / "reference_features.npy", X.astype("float16"))
    save_json({"method": "mean cosine similarity to the k nearest training photos (EfficientNetB3 features)",
               "k": KNN, "threshold": cut, "keep_rate_target": OOD_KEEP,
               "feature_layer": backbone.name, "reference_file": "reference_features.npy"}, out / "ood.json")
    save_json([{"index": i, "code": c, "name": CLASS_INFO[c].name, "risk_level": CLASS_INFO[c].risk_level}
               for i, c in enumerate(CLASSES)], out / "labels.json")
    save_json(PreprocessConfig(image_size=SIZE, crop="center_square", tta=("hflip",)).to_dict(),
              out / "preprocess_config.json")
    save_json({"validation": cv, "test": cv}, out / "metrics.json")
    plot_confusion(np.array(cv["confusion_matrix"]), CLASSES, out / "confusion_matrix_cv.png", "5-fold CV")
    counts = df.groupby(["dx", "source"]).size().unstack(fill_value=0)
    run_cfg = {"backbone": BACKBONE, "size": SIZE, "C": C, "classes": CLASSES, "tta": ["hflip"],
               "scin_cap": SCIN_CAP, "ood_k": KNN, "ood_keep": OOD_KEEP}
    save_json({
        "version": version, "domain": "general", "architecture": "efficientnetb3+logreg+knn-ood",
        "model_file": "model.keras", "model_sha256": sha256_file(out / "model.keras"),
        "num_classes": len(CLASSES), "classes": CLASSES, "image_size": SIZE,
        "confidence_threshold": THRESHOLD, "selection_metric": "5-fold grouped CV",
        "selection_value_val": cv["macro_f1"], "config_hash": config_hash(run_cfg), "config": run_cfg,
        "group_column": "case/person", "splits_fingerprint": "5-fold-cv-seed42",
        "dataset": {"name": "Supplied rash/acne photos + SCIN (Google Research) subset",
                    "license": "supplied photos: check source licence; SCIN: SCIN Data Use License",
                    "attribution": "Supplied SkinRash/acne photos; SCIN, Google Research & Stanford Medicine",
                    "counts": json.loads(counts.to_json())},
        "environment": environment_info(),
        "intended_use": "Research/education, non-commercial. Not a medical device.",
    }, out / "manifest.json")
    (out / "MODEL_CARD.md").write_text(
        f"# Model card: {version}\n\n- Rash checker: {', '.join(CLASSES)} ({len(df)} photos: supplied + SCIN)\n"
        f"- EfficientNetB3 features (300 px, + flipped view) and logistic regression\n"
        f"- Unfamiliar-photo check: k={KNN} nearest-neighbour cosine similarity, cut-off {cut:.4f} "
        f"(lets {OOD_KEEP:.0%} of genuine photos through)\n"
        f"- Reported results: 5-fold cross-validation grouped by person/case (each photo tested once, unseen)\n"
        f"- Accuracy on the supplied photos alone: {cv['supplied_photos_accuracy']:.1%}\n"
        f"- 'Not sure' below {THRESHOLD:.0%} confidence\n\n" + metrics_markdown(cv, CLASSES, "Cross-validated results")
        + "\n\n**Small dataset; not a medical device.**\n", encoding="utf-8")
    (resolve("ml/artifacts/face/models") / "LATEST").write_text(version, encoding="utf-8")
    print(f"exported {out}")


if __name__ == "__main__":
    main()
