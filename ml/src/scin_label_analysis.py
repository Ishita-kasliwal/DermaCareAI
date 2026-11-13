"""Analyse SCIN dermatologist labels to decide which skin conditions have enough data to train on.

    python -m ml.src.scin_label_analysis [--min-weight 0.5] [--min-cases 60]

Only reads scin_cases.csv + scin_labels.csv (no images needed). Writes a summary to
ml/artifacts/reports/scin/condition_counts.csv.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter

import pandas as pd

from ml.src.utils import resolve

ROOT = resolve("ml/data/raw/SCIN")


def parse_weights(s) -> dict:
    if not isinstance(s, str) or not s.strip():
        return {}
    try:
        d = ast.literal_eval(s)
        return d if isinstance(d, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-weight", type=float, default=0.5,
                    help="top condition must hold at least this share of the dermatologists' weight")
    ap.add_argument("--min-cases", type=int, default=60, help="minimum cases for a condition to qualify")
    args = ap.parse_args()

    cases = pd.read_csv(ROOT / "scin_cases.csv")
    labels = pd.read_csv(ROOT / "scin_labels.csv")
    df = cases.merge(labels, on="case_id", how="left")
    img_cols = [c for c in df.columns if c.startswith("image_") and c.endswith("_path")]
    df["n_images"] = df[img_cols].notna().sum(axis=1)

    print(f"cases: {len(df)}   images referenced: {int(df['n_images'].sum())}")
    df["weights"] = df["weighted_skin_condition_label"].map(parse_weights)
    has_label = df["weights"].map(bool)
    print(f"cases with a dermatologist condition label: {int(has_label.sum())}")

    lab = df[has_label].copy()
    lab["top"] = lab["weights"].map(lambda d: max(d, key=d.get))
    lab["top_w"] = lab["weights"].map(lambda d: max(d.values()))
    lab["n_conditions"] = lab["weights"].map(len)
    print(f"  ...with one condition only: {int((lab['n_conditions'] == 1).sum())}")
    confident = lab[lab["top_w"] >= args.min_weight]
    print(f"  ...where the top condition has >= {args.min_weight:.0%} of the weight: {len(confident)} "
          f"cases, {int(confident['n_images'].sum())} images")

    counts = (confident.groupby("top")
              .agg(cases=("case_id", "count"), images=("n_images", "sum"),
                   mean_top_weight=("top_w", "mean"))
              .sort_values("cases", ascending=False))
    counts["qualifies"] = counts["cases"] >= args.min_cases
    out = resolve("ml/artifacts/reports/scin")
    out.mkdir(parents=True, exist_ok=True)
    counts.to_csv(out / "condition_counts.csv")

    print(f"\ndistinct top conditions: {len(counts)}")
    q = counts[counts["qualifies"]]
    print(f"conditions with >= {args.min_cases} confidently-labelled cases: {len(q)} "
          f"({int(q['cases'].sum())} cases, {int(q['images'].sum())} images)\n")
    print(counts.head(40).to_string(float_format=lambda v: f"{v:.2f}"))

    if "fitzpatrick_skin_type" in df.columns:
        print("\nself-reported skin type (all cases):",
              dict(Counter(df["fitzpatrick_skin_type"].fillna("NONE")).most_common()))


if __name__ == "__main__":
    main()
