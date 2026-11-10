"""Exploratory data analysis. Every number is computed from the downloaded dataset.

    python -m ml.src.eda --config ml/configs/train.yaml

Outputs -> ml/artifacts/reports/eda/
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

from ml.src.dataset import DatasetNotFoundError, load_metadata  # noqa: E402
from ml.src.utils import load_config, resolve, save_json  # noqa: E402
from skinai_ml.classes import CLASS_INFO  # noqa: E402


def run_eda(cfg: dict, samples_per_class: int = 5) -> dict:
    df = load_metadata(cfg)
    out = resolve(cfg["output_dir"]) / "reports" / "eda"
    out.mkdir(parents=True, exist_ok=True)
    classes = cfg["data"]["classes"]
    group_col = cfg["data"].get("group_column", "lesion_id")

    counts = df["dx"].value_counts().reindex(classes).fillna(0).astype(int)
    pct = (counts / counts.sum() * 100).round(2)
    imgs_per_group = df.groupby(group_col).size()

    # image dimensions (header read only; fast)
    sizes = pd.Series([Image.open(p).size for p in df["path"]])
    size_counts = sizes.value_counts().head(10)

    stats = {
        "total_images": int(len(df)),
        "total_groups": int(df[group_col].nunique()),
        "group_column": group_col,
        "class_counts": counts.to_dict(),
        "class_percent": pct.to_dict(),
        "imbalance_ratio_max_min": round(float(counts.max() / max(counts.min(), 1)), 2),
        "images_per_group": {
            "mean": round(float(imgs_per_group.mean()), 3),
            "max": int(imgs_per_group.max()),
            "groups_with_multiple_images": int((imgs_per_group > 1).sum()),
        },
        "image_sizes_top": {f"{w}x{h}": int(n) for (w, h), n in size_counts.items()},
    }
    for col in ("dx_type", "sex", "localization"):
        if col in df.columns:
            stats[col] = df[col].fillna("unknown").value_counts().to_dict()
            if col == "dx_type":
                stats["dx_type_by_class"] = (
                    pd.crosstab(df["dx"], df["dx_type"]).reindex(classes).fillna(0).astype(int)
                    .to_dict(orient="index")
                )
    if "age" in df.columns:
        a = df["age"].dropna()
        stats["age"] = {"missing": int(df["age"].isna().sum()), "mean": round(float(a.mean()), 1),
                        "min": float(a.min()), "max": float(a.max())}
    save_json(stats, out / "eda_stats.json")

    # --- plots
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(counts.index, counts.values, color="#3b6ea5")
    for i, v in enumerate(counts.values):
        ax.text(i, v, f"{v}\n({pct.iloc[i]}%)", ha="center", va="bottom", fontsize=8)
    ax.set_title("HAM10000 class distribution (images)")
    ax.set_ylabel("images")
    fig.tight_layout()
    fig.savefig(out / "class_distribution.png", dpi=120)
    plt.close(fig)

    if "age" in df.columns:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.hist(df["age"].dropna(), bins=18, color="#5a8f69")
        ax.set_title("Age distribution")
        fig.tight_layout()
        fig.savefig(out / "age_distribution.png", dpi=120)
        plt.close(fig)

    # --- sample grid (real images, fixed seed)
    rng = np.random.default_rng(cfg["seed"])
    fig, axes = plt.subplots(len(classes), samples_per_class,
                             figsize=(2.2 * samples_per_class, 2.2 * len(classes)))
    for r, c in enumerate(classes):
        paths = df.loc[df["dx"] == c, "path"].values
        pick = rng.choice(paths, size=min(samples_per_class, len(paths)), replace=False)
        for k in range(samples_per_class):
            a = axes[r, k]
            a.axis("off")
            if k < len(pick):
                a.imshow(Image.open(pick[k]).convert("RGB"))
            if k == 0:
                a.set_title(f"{c}: {CLASS_INFO[c].name}"[:38], fontsize=8, loc="left")
    fig.suptitle("Sample images per class (HAM10000, CC BY-NC 4.0, ViDIR Group, MedUni Vienna)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "sample_images.png", dpi=110)
    plt.close(fig)

    # --- markdown summary
    lines = ["# EDA summary (computed)", "", f"Images: {stats['total_images']}  ",
             f"Groups ({group_col}): {stats['total_groups']}  ",
             f"Max/min class ratio: {stats['imbalance_ratio_max_min']}", "",
             "| class | images | % |", "|---|---|---|"]
    lines += [f"| {c} | {counts[c]} | {pct[c]} |" for c in classes]
    lines += ["", "![classes](class_distribution.png)", "", "![samples](sample_images.png)"]
    (out / "EDA.md").write_text("\n".join(lines), encoding="utf-8")
    return stats


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    args = ap.parse_args()
    try:
        stats = run_eda(load_config(args.config))
    except DatasetNotFoundError as e:
        raise SystemExit(str(e)) from None
    import json

    print(json.dumps({k: stats[k] for k in ("total_images", "total_groups", "class_counts")}, indent=2))


if __name__ == "__main__":
    _main()
