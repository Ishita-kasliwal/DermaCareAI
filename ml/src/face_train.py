"""Train + export the rash checker from the user-provided rash dataset (dermatitis, eczema, ringworm).

    python -m ml.src.face_train

Method (chosen by 5-fold grouped cross-validation, see ml/src/face_cv.py): frozen ImageNet EfficientNetB3
features at 300 px, averaged over the original + horizontally flipped photo, then a regularised logistic
regression. The StandardScaler + logistic regression are folded into one Dense softmax layer, so the
exported Keras model gives exactly the same probabilities and loads in the app like any other model.

Reported metrics are the 5-fold grouped cross-validated predictions (every photo predicted once by a model
that never saw it). The final model is then fitted on all photos.
"""

from __future__ import annotations

import keras
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

from ml.src.evaluate import compute_metrics, metrics_markdown, plot_confusion
from ml.src.face_cv import ROOT, features
from ml.src.utils import config_hash, environment_info, resolve, save_json, sha256_file, timestamp
from skinai_ml.classes import CLASS_INFO

CLASSES = ["dermatitis", "eczema", "ringworm"]
BACKBONE, SIZE, C = "efficientnetb3", 300, 0.05
THRESHOLD = 0.70


def main() -> None:
    df = pd.read_csv(ROOT / "face_metadata.csv")
    df = df[df["dx"].isin(CLASSES)].reset_index(drop=True)
    df["path"] = df["image_id"].map(lambda i: str(ROOT / "images" / f"{i}.jpg"))
    y = df["dx"].map({c: i for i, c in enumerate(CLASSES)}).values
    X = features(df["path"], BACKBONE, SIZE)

    # ---- honest estimate: grouped 5-fold CV
    proba = np.zeros((len(df), len(CLASSES)))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=42).split(X, y, df["lesion_id"]):
        sc = StandardScaler().fit(X[tr])
        lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X[tr]), y[tr])
        proba[te] = lr.predict_proba(sc.transform(X[te]))
    cv = compute_metrics(y, proba, CLASSES)
    cv["split"] = "5-fold grouped cross-validation"

    # ---- final model on all photos, folded into a Keras Dense layer
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced").fit(sc.transform(X), y)
    W = (lr.coef_ / sc.scale_).T.astype("float32")                       # (features, classes)
    b = (lr.intercept_ - (lr.coef_ * sc.mean_ / sc.scale_).sum(1)).astype("float32")

    inputs = keras.Input((SIZE, SIZE, 3), dtype="float32", name="image")
    backbone = keras.applications.EfficientNetB3(include_top=False, weights="imagenet", pooling="avg",
                                                 input_shape=(SIZE, SIZE, 3))
    x = backbone(inputs, training=False)
    dense = keras.layers.Dense(len(CLASSES), activation="softmax", dtype="float32", name="probs")
    model = keras.Model(inputs, dense(x), name="rash_checker_effb3")
    dense.set_weights([W, b])

    # sanity: Keras model reproduces sklearn on a few photos (without TTA, single view)
    import tensorflow as tf

    from skinai_ml.preprocess import PreprocessConfig, load_and_preprocess_file
    cfg = PreprocessConfig(image_size=SIZE, crop="center_square")
    batch = tf.stack([tf.cast(load_and_preprocess_file(p, cfg), tf.float32) for p in df["path"][:8]])
    k = np.asarray(model(batch))
    s = lr.predict_proba(sc.transform(np.asarray(backbone(batch))))
    assert np.allclose(k, s, atol=1e-4), "folded Keras model does not match sklearn"

    version = f"rashcheck-effb3-{timestamp()}"
    out = resolve("ml/artifacts/face/models") / version
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    save_json([{"index": i, "code": c, "name": CLASS_INFO[c].name, "risk_level": CLASS_INFO[c].risk_level}
               for i, c in enumerate(CLASSES)], out / "labels.json")
    pre = PreprocessConfig(image_size=SIZE, crop="center_square", tta=("hflip",)).to_dict()
    save_json(pre, out / "preprocess_config.json")
    save_json({"validation": cv, "test": cv}, out / "metrics.json")
    plot_confusion(np.array(cv["confusion_matrix"]), CLASSES, out / "confusion_matrix_cv.png", "5-fold CV")
    run_cfg = {"backbone": BACKBONE, "size": SIZE, "C": C, "classes": CLASSES, "tta": ["hflip"]}
    save_json({
        "version": version, "domain": "general", "architecture": "efficientnetb3+logreg",
        "model_file": "model.keras", "model_sha256": sha256_file(out / "model.keras"),
        "num_classes": len(CLASSES), "classes": CLASSES, "image_size": SIZE,
        "confidence_threshold": THRESHOLD, "selection_metric": "5-fold grouped CV",
        "selection_value_val": cv["macro_f1"], "config_hash": config_hash(run_cfg), "config": run_cfg,
        "group_column": "lesion_id", "splits_fingerprint": "5-fold-cv-seed42",
        "dataset": {"name": "User-provided skin rash dataset (dermatitis, eczema, ringworm)",
                    "license": "provided by the project owner; check its source licence before sharing",
                    "attribution": "SkinRash dataset supplied by the project owner"},
        "environment": environment_info(),
        "intended_use": "Research/education, non-commercial. Not a medical device.",
    }, out / "manifest.json")
    (out / "MODEL_CARD.md").write_text(
        f"# Model card: {version}\n\n- Rash checker: {', '.join(CLASSES)} ({len(df)} photos)\n"
        f"- EfficientNetB3 features (300 px, + flipped view) and logistic regression\n"
        f"- Reported results: 5-fold cross-validation grouped by photo/person (each photo tested once, unseen)\n"
        f"- 'Not sure' below {THRESHOLD:.0%} confidence\n\n" + metrics_markdown(cv, CLASSES, "Cross-validated results")
        + "\n\n**Small dataset; not a medical device.**\n", encoding="utf-8")
    (resolve("ml/artifacts/face/models") / "LATEST").write_text(version, encoding="utf-8")
    conf = proba.max(1)
    m = conf >= THRESHOLD
    print(f"exported {out}")
    print(f"CV accuracy {cv['accuracy']:.3f} | balanced {cv['balanced_accuracy']:.3f} | "
          f"when >= {THRESHOLD:.0%} sure: {m.mean():.0%} of photos, accuracy {(proba[m].argmax(1) == y[m]).mean():.3f}")


if __name__ == "__main__":
    main()
