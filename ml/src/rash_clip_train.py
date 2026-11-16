"""Rash checker v4: CLIP image features + logistic regression + a "not a skin problem" photo check.

    python -m ml.src.rash_clip_train [--probe photo.jpg ...] [--cv-only]

Why CLIP: the earlier ImageNet-feature models scored well in cross-validation but failed on everyday internet/
phone photos (acne called eczema, a selfie called ringworm). CLIP (ViT-B/16, keras-hub preset
clip_vit_base_patch16) was pre-trained on a very wide range of photos and reads such photos much better.

Data
- the supplied acne/rash photos + the prepared SCIN subset (acne, contact dermatitis -> dermatitis,
  eczema, fungal -> ringworm), exactly as ml/src/rash_train.py builds it;
- three Roboflow Universe sets (CC BY 4.0, downloaded by ml/src/roboflow_download.py, approved 2026-11-16):
  skin-analysis (Acne -> acne, Pigmentation -> dark_spots, Redness -> redness; multi-label photos skipped),
  basic-wound-classify (abrasion + laceration -> scratches, normal skin -> healthy).
  Roboflow stores 3 altered copies of each photo; only one copy per original is used and copies share a group.
  Dermatoscope close-ups inside "Pigmentation" (moles, possible melanoma) are removed with a CLIP text check so
  the rash checker never learns to call them "dark spots" - those belong to the mole checker.
  Near-duplicate photos (CLIP cosine > 0.95) are put in the same cross-validation group.
- Not used: the skin-type set (dry/oily/normal selfies): 39% in cross-validation against 33% by chance, so
  "dry skin" cannot be learned from those photos.

Photo check: the photo's CLIP embedding is compared with fixed text descriptions (see GOOD/OTHER). If it
looks more like "a selfie", "an object", "clear healthy skin" ... than a skin problem, the 5th answer
"unfamiliar" wins. Its bias is set during cross-validation so that 95% of genuine photos still get a condition.

Reported metrics: 5-fold cross-validation grouped by person/case, before the photo check (8 conditions), plus how
many genuine photos the photo check wrongly turns away.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import StratifiedGroupKFold

from ml.src import rash_train as R
from ml.src.utils import resolve

PRESET = "clip_vit_base_patch16"
SIZE, C, THRESHOLD, KEEP = 224, 0.05, 0.60, 0.95
CLASSES = R.CLASSES + ["dark_spots", "redness", "scratches", "healthy"]
RF = resolve("ml/data/raw/ROBOFLOW")
RF_MAP = [("skin_analysis", "Acne", "acne"), ("skin_analysis", "Pigmentation", "dark_spots"),
          ("skin_analysis", "Redness", "redness"), ("wounds", "abrasion", "scratches"),
          ("wounds", "laceration", "scratches"), ("wounds", "normal skin", "healthy")]
DERMOSCOPY = ["a dermoscopy image of a mole or skin lesion", "a close-up photo of skin on a person's face or body"]
DUP_COS = 0.95
GOOD = ["a close-up photo of skin with acne or pimples", "a close-up photo of a red itchy skin rash",
        "a close-up photo of eczema on the skin", "a close-up photo of a ringworm fungal infection on the skin",
        "a close-up photo of irritated red skin", "a close-up photo of a skin problem",
        "a close-up photo of dark spots or pigmentation on the skin", "a close-up photo of red flushed cheeks",
        "a close-up photo of a scrape, scratch or cut on the skin", "a close-up photo of normal healthy skin"]
OTHER = ["a selfie of a person", "a photo of a person's whole face", "a photo of a person with clear healthy skin",
         "a photo of a room, wall or object", "a photo of an animal", "a screenshot or drawing", "a photo of food",
         "a dermoscopy image of a mole"]
# CLIP image normalisation (from the preset's image_converter.json): x * SCALE + OFFSET, x in 0..255
SCALE = [0.014598426619242919, 0.015007768493717055, 0.014220065717024086]
OFFSET = [-1.79226253374815, -1.7520971281645974, -1.4802197687835659]


def preprocess_cfg(tta=()):
    from skinai_ml.preprocess import PreprocessConfig

    return PreprocessConfig(image_size=SIZE, crop="center_square", resize_method="bicubic", tta=tuple(tta))


def clip_parts():
    import keras
    import keras_hub

    bb = keras_hub.models.CLIPBackbone.from_preset(PRESET)
    inp = keras.Input((SIZE, SIZE, 3), dtype="float32", name="image")
    x = keras.layers.Rescaling(scale=np.array(SCALE, "float32"), offset=np.array(OFFSET, "float32"),
                               name="clip_normalise")(inp)
    x = bb.vision_encoder({"images": x})
    x = bb.vision_pooler(x)
    emb = bb.vision_projection(x)
    return bb, keras.Model(inp, emb, name="clip_image_embedding")


def text_embeddings(bb, texts=None) -> np.ndarray:
    import keras_hub

    d = os.path.expanduser(f"~/.cache/kagglehub/models/keras/clip/keras/{PRESET}/3/assets/tokenizer")
    if not os.path.exists(d + "/vocabulary.json"):
        import kagglehub

        for f in ("assets/tokenizer/vocabulary.json", "assets/tokenizer/merges.txt"):
            kagglehub.model_download(f"keras/clip/keras/{PRESET}/3", path=f)
    vocab = json.load(open(d + "/vocabulary.json", encoding="utf-8"))
    merges = [ln.rstrip("\n") for ln in open(d + "/merges.txt", encoding="utf-8")
              if ln.strip() and not ln.startswith("#version")]

    class Tok(keras_hub.tokenizers.CLIPTokenizer):  # works around a keras-hub 0.33 loading bug
        def _set_vocabulary_and_merges_tokenizers(self, vocabulary, merges):
            object.__setattr__(self, "vocabulary", dict(vocabulary))
            object.__setattr__(self, "merges", list(merges))
            super()._set_vocabulary_and_merges_tokenizers(vocabulary, merges)

    pre = keras_hub.models.CLIPPreprocessor(tokenizer=Tok(vocabulary=vocab, merges=merges), sequence_length=77)
    tok = pre({"images": None, "prompts": list(texts or GOOD + OTHER)})["token_ids"]
    t = np.array(bb.get_text_embeddings(tok), dtype="float32")
    return t / np.linalg.norm(t, axis=1, keepdims=True)


def embed(model, paths) -> np.ndarray:
    import tensorflow as tf

    from skinai_ml.preprocess import load_and_preprocess_file

    cfg = preprocess_cfg()
    ds = tf.data.Dataset.from_tensor_slices(list(paths)).map(
        lambda p: tf.cast(load_and_preprocess_file(p, cfg), tf.float32)).batch(16)
    a = model.predict(ds, verbose=0)
    b = model.predict(ds.map(tf.image.flip_left_right), verbose=0)
    return ((a + b) / 2).astype("float32")


def cached_embed(model, paths) -> np.ndarray:
    store = resolve("ml/data/processed/cache/feat_clip_b16_app.npz")
    known = {}
    if store.exists():
        z = np.load(store)
        known = dict(zip(z["paths"].tolist(), z["feats"], strict=True))
    todo = [p for p in paths if p not in known]
    if todo:
        print(f"CLIP features for {len(todo)} photos ...", flush=True)
        known.update(zip(todo, embed(model, todo), strict=True))
        np.savez(store, paths=np.array(list(known)), feats=np.stack(list(known.values())))
    return np.stack([known[p] for p in paths])


def roboflow_rows() -> pd.DataFrame:
    """One photo per original (Roboflow keeps 3 altered copies with the same name before '.rf.')."""
    rows = []
    for ds, folder, dx in RF_MAP:
        seen = set()
        for f in sorted((RF / ds).glob(f"*/{folder}/*.jpg")):
            stem = f.name.split(".rf.")[0]
            if stem not in seen:
                seen.add(stem)
                rows.append({"path": str(f), "dx": dx, "source": f"roboflow_{ds}", "group": f"r_{ds}_{stem}"})
    return pd.DataFrame(rows)


def build_table(bb, emb_model):
    """All training photos + their CLIP features, cleaned and grouped (see the module docstring)."""
    df = pd.concat([R.build_table(), roboflow_rows()], ignore_index=True)
    F = cached_embed(emb_model, list(df["path"]))
    f = F / np.linalg.norm(F, axis=1, keepdims=True)
    zs = f @ text_embeddings(bb, DERMOSCOPY).T
    drop = (zs[:, 0] > zs[:, 1]) & (df["dx"] == "dark_spots").values
    print(f"removed {drop.sum()} dermatoscope close-ups from dark_spots")
    df, F = df[~drop].reset_index(drop=True), F[~drop]

    # near-duplicates (also across sources) must stay in the same fold: union-find on cosine similarity
    f = F / np.linalg.norm(F, axis=1, keepdims=True)
    parent = list(range(len(df)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in zip(*np.where(np.triu(f @ f.T, 1) > DUP_COS), strict=True):
        parent[find(i)] = find(j)
    first = {}
    df["group"] = [first.setdefault(find(i), g) for i, g in enumerate(df["group"])]
    return df, F


def gate_margin(F: np.ndarray, T: np.ndarray) -> np.ndarray:
    """logsumexp(good) - logsumexp(other) of the CLIP text similarities (before the bias)."""
    from scipy.special import logsumexp

    f = F / np.linalg.norm(F, axis=1, keepdims=True)
    lg = 100.0 * f @ T.T
    return logsumexp(lg[:, : len(GOOD)], axis=1) - logsumexp(lg[:, len(GOOD):], axis=1)


def combine(probs, margin, bias):
    p = 1 / (1 + np.exp(-(margin + bias)))
    return np.concatenate([probs * p[:, None], (1 - p)[:, None]], axis=1)


def choose_bias(probs, margin) -> float:
    """Smallest bias that lets KEEP of the genuine photos get a condition (not 'unfamiliar') as top answer."""
    for bias in np.arange(-5, 15.01, 0.05):
        out = combine(probs, margin, bias)
        if (out.argmax(1) < len(CLASSES)).mean() >= KEEP:
            return float(round(bias, 2))
    return 15.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv-only", action="store_true")
    ap.add_argument("--probe", nargs="*", default=[])
    args = ap.parse_args()

    bb, emb_model = clip_parts()
    df, F = build_table(bb, emb_model)
    print(df.groupby(["dx", "source"]).size().unstack(fill_value=0).to_string())
    T = text_embeddings(bb)
    y = df["dx"].map({c: i for i, c in enumerate(CLASSES)}).values
    margin = gate_margin(F, T)

    R.C = C
    proba = np.zeros((len(df), len(CLASSES)))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=42).split(F, y, df["group"]):
        sc, lr = R.fit(F[tr], y[tr])
        proba[te] = lr.predict_proba(sc.transform(F[te]))
    bias = choose_bias(proba, margin)
    pred = proba.argmax(1)
    sup = (df["source"] == "supplied").values
    conf = proba.max(1)
    sure = conf >= THRESHOLD
    final = combine(proba, margin, bias)
    turned_away = float((final.argmax(1) == len(CLASSES)).mean())
    summary = {
        "accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "supplied_photos_accuracy": float(accuracy_score(y[sup], pred[sup])),
        "sure_threshold": THRESHOLD, "sure_coverage": float(sure.mean()),
        "sure_accuracy": float(accuracy_score(y[sure], pred[sure])),
        "photo_check_bias": bias, "genuine_photos_turned_away": turned_away,
        "recall_per_condition": {c: float((pred[y == i] == i).mean()) for i, c in enumerate(CLASSES)},
    }
    print(json.dumps(summary, indent=2))

    sc, lr = R.fit(F, y)
    if args.probe:
        P = embed(emb_model, args.probe)
        out = combine(lr.predict_proba(sc.transform(P)), gate_margin(P, T), bias)
        names = CLASSES + ["unfamiliar"]
        for p, row in zip(args.probe, out, strict=True):
            top = ", ".join(f"{names[i]} {row[i]:.2f}" for i in row.argsort()[::-1][:2])
            print(f"probe ...{p[-30:]}: {top}")
    if not args.cv_only:
        export(df, F, y, proba, sc, lr, T, bias, emb_model, summary)


def export(df, F, y, proba, sc, lr, T, bias, emb_model, summary) -> None:
    import keras
    import tensorflow as tf

    from ml.src.evaluate import compute_metrics, metrics_markdown, plot_confusion
    from ml.src.utils import config_hash, environment_info, save_json, sha256_file, timestamp
    from skinai_ml.classes import CLASS_INFO
    from skinai_ml.layers import SkinPhotoGate
    from skinai_ml.preprocess import load_and_preprocess_file

    cv = compute_metrics(y, proba, CLASSES)
    cv["split"] = f"5-fold grouped cross-validation ({len(CLASSES)} conditions, before the photo check)"
    cv.update({k: v for k, v in summary.items() if k not in cv})

    W = (lr.coef_ / sc.scale_).T.astype("float32")
    b = (lr.intercept_ - (lr.coef_ * sc.mean_ / sc.scale_).sum(1)).astype("float32")
    emb = emb_model.output
    dense = keras.layers.Dense(len(CLASSES), activation="softmax", dtype="float32", name="condition_probs")
    gate = SkinPhotoGate(n_texts=len(T), n_good=len(GOOD), dim=T.shape[1], bias=bias, name="photo_check")
    model = keras.Model(emb_model.input, gate([emb, dense(emb)]), name="rash_checker_clip")
    dense.set_weights([W, b])
    gate.set_weights([T])

    cfg = preprocess_cfg()
    batch = tf.stack([tf.cast(load_and_preprocess_file(p, cfg), tf.float32) for p in df["path"][:6]])
    e = np.asarray(emb_model(batch))
    ref = combine(lr.predict_proba(sc.transform(e)), gate_margin(e, T), bias)
    assert np.allclose(np.asarray(model(batch)), ref, atol=1e-3), "exported model does not match sklearn"

    version = f"rashcheck-clip-{timestamp()}"
    out = resolve("ml/artifacts/face/models") / version
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    codes = CLASSES + ["unfamiliar"]
    save_json([{"index": i, "code": c, "name": CLASS_INFO[c].name, "risk_level": CLASS_INFO[c].risk_level}
               for i, c in enumerate(codes)], out / "labels.json")
    save_json(preprocess_cfg(("hflip",)).to_dict(), out / "preprocess_config.json")
    save_json({"validation": cv, "test": cv}, out / "metrics.json")
    plot_confusion(np.array(cv["confusion_matrix"]), CLASSES, out / "confusion_matrix_cv.png", "5-fold CV")
    counts = df.groupby(["dx", "source"]).size().unstack(fill_value=0)
    run_cfg = {"backbone": PRESET, "size": SIZE, "C": C, "classes": CLASSES, "tta": ["hflip"],
               "scin_cap": R.SCIN_CAP, "good_texts": GOOD, "other_texts": OTHER, "keep": KEEP,
               "roboflow_map": RF_MAP, "duplicate_cosine": DUP_COS}
    save_json({
        "version": version, "domain": "general", "architecture": "clip-vit-b16+logreg+photo-check",
        "requires": ["keras_hub"], "gradcam": False,
        "model_file": "model.keras", "model_sha256": sha256_file(out / "model.keras"),
        "num_classes": len(codes), "classes": codes, "image_size": SIZE,
        "confidence_threshold": THRESHOLD, "selection_metric": "5-fold grouped CV",
        "selection_value_val": cv["macro_f1"], "config_hash": config_hash(run_cfg), "config": run_cfg,
        "group_column": "case/person", "splits_fingerprint": "5-fold-cv-seed42",
        "dataset": {"name": "Supplied rash/acne photos + SCIN subset + Roboflow Universe skin-analysis and "
                            "basic-wound-classify",
                    "license": "supplied photos: check source licence; SCIN: SCIN Data Use License; Roboflow "
                               "sets: CC BY 4.0 (skin-analysis acne photos originate from DermNet, non-commercial "
                               "educational use); CLIP weights: MIT (OpenAI) via keras-hub",
                    "attribution": "Supplied SkinRash/acne photos; SCIN, Google Research & Stanford Medicine; "
                                   "'Skin analysis' by image-classification-q4nkn and 'basic-wound-classify' by "
                                   "clinicvision on Roboflow Universe; DermNet (dermnetnz.org)",
                    "counts": json.loads(counts.to_json())},
        "environment": environment_info(),
        "intended_use": "Research/education, non-commercial. Not a medical device.",
    }, out / "manifest.json")
    (out / "MODEL_CARD.md").write_text(
        f"# Model card: {version}\n\n- Rash checker: {', '.join(CLASSES)} + 'not a skin problem the AI knows'\n"
        f"- CLIP ViT-B/16 image features (224 px, + flipped view) and logistic regression; {len(df)} photos\n"
        f"- Photo check: CLIP text comparison, bias {bias} (turns away {summary['genuine_photos_turned_away']:.1%} "
        f"of genuine photos in cross-validation)\n"
        f"- 5-fold cross-validation grouped by person/case: accuracy {summary['accuracy']:.1%}, "
        f"supplied photos {summary['supplied_photos_accuracy']:.1%}, when >= {THRESHOLD:.0%} sure "
        f"{summary['sure_accuracy']:.1%} (covers {summary['sure_coverage']:.0%})\n\n"
        + metrics_markdown(cv, CLASSES, "Cross-validated results") + "\n\n**Not a medical device.**\n",
        encoding="utf-8")
    (resolve("ml/artifacts/face/models") / "LATEST").write_text(version, encoding="utf-8")
    print(f"exported {out}")


if __name__ == "__main__":
    main()
