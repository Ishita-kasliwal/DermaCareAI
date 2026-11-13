"""Dataset loading and leakage-safe splitting.

    python -m ml.src.dataset --config ml/configs/train.yaml      # creates/validates split CSVs
"""

from __future__ import annotations

import argparse
import hashlib

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from ml.src.utils import load_config, resolve, save_json

REQUIRED_COLUMNS = ("image_id", "dx")

DOWNLOAD_HELP = """
HAM10000 was not found at: {root}

This pipeline never substitutes fabricated data. Download the real dataset first:

  Option A (script, verifies MD5):   .\\scripts\\download_ham10000.ps1
  Option B (manual):  https://doi.org/10.7910/DVN/DBW86T
     - HAM10000_images_part_1.zip, HAM10000_images_part_2.zip  -> extract into {root}
     - HAM10000_metadata (Original File Format, CSV) -> {root}\\HAM10000_metadata.csv

License: CC BY-NC 4.0 (non-commercial, attribution). See docs/DATASETS.md.
"""


class DatasetNotFoundError(FileNotFoundError):
    pass


def load_metadata(cfg: dict) -> pd.DataFrame:
    """Read metadata, attach image paths, validate. Raises with download help if missing."""
    root = resolve(cfg["data"]["root"])
    meta_path = root / cfg["data"]["metadata_csv"]
    if not meta_path.exists():
        raise DatasetNotFoundError(DOWNLOAD_HELP.format(root=root))

    group_col = cfg["data"].get("group_column", "lesion_id")
    # IDs are text (SCIN ids look like large negative integers; never let pandas parse them)
    df = pd.read_csv(meta_path, dtype={"image_id": str, group_col: str})
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"metadata is missing columns {missing}; found {list(df.columns)}")
    if group_col not in df.columns:
        raise ValueError(f"group column '{group_col}' not in metadata")

    patterns = cfg["data"].get("image_glob", ["**/*.jpg"])
    index = {p.stem: p for pattern in patterns for p in root.glob(pattern)}
    if not index:
        raise DatasetNotFoundError(DOWNLOAD_HELP.format(root=root))
    df["path"] = df["image_id"].map(lambda i: str(index[i]) if i in index else None)

    n_missing = int(df["path"].isna().sum())
    if n_missing:
        examples = df.loc[df["path"].isna(), "image_id"].head(5).tolist()
        raise FileNotFoundError(f"{n_missing} images listed in metadata are missing, e.g. {examples}")

    classes = cfg["data"]["classes"]
    unknown = sorted(set(df["dx"]) - set(classes))
    if unknown:
        raise ValueError(f"metadata contains classes not in config: {unknown}")
    df["label"] = df["dx"].map({c: i for i, c in enumerate(classes)}).astype(int)
    return df


def make_splits(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Stratified, GROUPED split: every image of a group (lesion/patient) lands in one split."""
    seed = int(cfg["seed"])
    group_col = cfg["data"].get("group_column", "lesion_id")
    fr = cfg["data"]["split"]
    if not np.isclose(fr["train"] + fr["val"] + fr["test"], 1.0):
        raise ValueError("split fractions must sum to 1")

    df = df.copy()
    groups = df[group_col].astype(str).values
    y = df["label"].values

    # 1) carve out test
    n_test = max(2, round(1 / fr["test"]))
    sgkf = StratifiedGroupKFold(n_splits=n_test, shuffle=True, random_state=seed)
    trainval_idx, test_idx = next(sgkf.split(df, y, groups))

    # 2) carve val out of the remainder
    val_share = fr["val"] / (fr["train"] + fr["val"])
    n_val = max(2, round(1 / val_share))
    rest = df.iloc[trainval_idx]
    sgkf2 = StratifiedGroupKFold(n_splits=n_val, shuffle=True, random_state=seed)
    tr_rel, va_rel = next(sgkf2.split(rest, rest["label"].values, rest[group_col].astype(str).values))

    df["split"] = ""
    df.iloc[test_idx, df.columns.get_loc("split")] = "test"
    df.iloc[trainval_idx[tr_rel], df.columns.get_loc("split")] = "train"
    df.iloc[trainval_idx[va_rel], df.columns.get_loc("split")] = "val"
    assert (df["split"] != "").all()
    assert_no_group_leakage(df, group_col)
    return df


def assert_no_group_leakage(df: pd.DataFrame, group_col: str) -> None:
    per_group = df.groupby(group_col)["split"].nunique()
    leaked = per_group[per_group > 1]
    if len(leaked):
        raise AssertionError(f"{len(leaked)} groups appear in more than one split")


def split_summary(df: pd.DataFrame, cfg: dict) -> dict:
    classes = cfg["data"]["classes"]
    group_col = cfg["data"].get("group_column", "lesion_id")
    out = {"group_column": group_col, "total_images": len(df), "splits": {}}
    for s in ("train", "val", "test"):
        part = df[df["split"] == s]
        out["splits"][s] = {
            "images": len(part),
            "fraction": round(len(part) / len(df), 4),
            "groups": int(part[group_col].nunique()),
            "per_class": {c: int((part["dx"] == c).sum()) for c in classes},
        }
    return out


def splits_fingerprint(df: pd.DataFrame) -> str:
    key = "\n".join(f"{i},{s}" for i, s in sorted(zip(df["image_id"], df["split"], strict=True)))
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def get_or_create_splits(cfg: dict) -> pd.DataFrame:
    """Splits are written once and reused, so every model is trained/evaluated on identical data."""
    out_dir = resolve(cfg["output_dir"]) / "splits"
    split_csv = out_dir / f"splits_seed{cfg['seed']}.csv"
    df = load_metadata(cfg)
    if split_csv.exists():
        saved = pd.read_csv(split_csv, dtype={"image_id": str})[["image_id", "split"]]
        df = df.merge(saved, on="image_id", how="left")
        if df["split"].isna().any():
            raise ValueError(f"{split_csv} does not match the metadata; delete it to regenerate")
        assert_no_group_leakage(df, cfg["data"].get("group_column", "lesion_id"))
        return df
    df = make_splits(df, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    df[["image_id", cfg["data"].get("group_column", "lesion_id"), "dx", "split"]].to_csv(
        split_csv, index=False
    )
    summary = split_summary(df, cfg)
    summary["fingerprint"] = splits_fingerprint(df)
    save_json(summary, out_dir / f"splits_seed{cfg['seed']}_summary.json")
    return df


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ml/configs/train.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    try:
        df = get_or_create_splits(cfg)
    except DatasetNotFoundError as e:
        raise SystemExit(str(e)) from None
    import json

    print(json.dumps(split_summary(df, cfg), indent=2))


if __name__ == "__main__":
    _main()
