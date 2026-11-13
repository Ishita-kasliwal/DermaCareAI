"""Prepare the SCIN "general skin conditions" dataset.

    python -m ml.src.scin_prepare                 # select cases, download needed photos, write metadata
    python -m ml.src.scin_prepare --metadata-only # just (re)write the metadata CSV

Source: Google Research SCIN dataset, gs://dx-scin-public-data (SCIN Data Use License).
Only photos of cases in the configured condition groups are downloaded; every file is verified
against the MD5 published in the bucket listing. Re-running skips files already verified.
Re-identification of contributors is prohibited by the licence; we store no contributor data
beyond what is needed for training (condition, skin type, shot type).
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yaml

from ml.src.utils import resolve

BUCKET = "dx-scin-public-data"
LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
FILE_URL = f"https://storage.googleapis.com/{BUCKET}/"
ROOT = resolve("ml/data/raw/SCIN")
IMG_DIR = ROOT / "images"


def _weights(s) -> dict:
    try:
        d = ast.literal_eval(s) if isinstance(s, str) else {}
        return d if isinstance(d, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def select_cases(groups_cfg: dict) -> pd.DataFrame:
    """One row per (case, image) for cases whose top label maps to a qualifying group."""
    cases = pd.read_csv(ROOT / "scin_cases.csv", dtype={"case_id": str})
    labels = pd.read_csv(ROOT / "scin_labels.csv", dtype={"case_id": str})
    df = cases.merge(labels, on="case_id", how="inner")
    df["weights"] = df["weighted_skin_condition_label"].map(_weights)
    df = df[df["weights"].map(bool)].copy()
    df["top"] = df["weights"].map(lambda d: max(d, key=d.get))
    df["top_weight"] = df["weights"].map(lambda d: max(d.values()))
    to_group = {lab: g for g, spec in groups_cfg["groups"].items() for lab in spec["labels"]}
    df["dx"] = df["top"].map(to_group)
    df = df[(df["top_weight"] >= groups_cfg["min_weight"]) & df["dx"].notna()]
    counts = df["dx"].value_counts()
    keep = counts[counts >= groups_cfg["min_cases"]].index
    df = df[df["dx"].isin(keep)]

    rows = []
    for _, r in df.iterrows():
        for i in (1, 2, 3):
            path = r.get(f"image_{i}_path")
            if isinstance(path, str) and path:
                rows.append({
                    "lesion_id": f"case_{r['case_id']}",   # group column: all photos of a case stay together
                    "image_id": Path(path).stem,
                    "dx": r["dx"],
                    "dx_type": "dermatologist_panel",
                    "top_label": r["top"],
                    "top_weight": round(float(r["top_weight"]), 3),
                    "shot_type": r.get(f"image_{i}_shot_type"),
                    "skin_type": r.get("fitzpatrick_skin_type"),
                    "sex": r.get("sex_at_birth"),
                    "bucket_path": path,
                })
    return pd.DataFrame(rows)


def list_bucket_md5(prefix: str = "dataset/images/") -> dict[str, tuple[int, str]]:
    out, token = {}, None
    while True:
        q = {"prefix": prefix, "fields": "items(name,size,md5Hash),nextPageToken", "maxResults": "1000"}
        if token:
            q["pageToken"] = token
        with urllib.request.urlopen(LIST_URL + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            data = json.load(r)
        for it in data.get("items", []):
            out[it["name"]] = (int(it["size"]), it["md5Hash"])
        token = data.get("nextPageToken")
        if not token:
            return out


def _md5_b64(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return base64.b64encode(h.digest()).decode()


def download_one(bucket_path: str, size: int, md5: str, attempts: int = 30) -> str:
    dest = IMG_DIR / Path(bucket_path).name
    if dest.exists() and dest.stat().st_size == size and _md5_b64(dest) == md5:
        return "ok-cached"
    tmp = dest.with_suffix(".part")
    url = FILE_URL + urllib.parse.quote(bucket_path)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
            if tmp.stat().st_size == size and _md5_b64(tmp) == md5:
                tmp.replace(dest)
                return "downloaded"
        except Exception:  # network drop: back off and retry
            pass
        time.sleep(min(60, 3 * attempt))
    tmp.unlink(missing_ok=True)
    return "failed"


def dedupe_shared_photos(meta: pd.DataFrame) -> pd.DataFrame:
    """SCIN has a few identical photos in more than one case. To prevent train/test leakage:
    - photos whose cases disagree on the condition are dropped (ambiguous);
    - other duplicates are kept once;
    - cases that share a photo are merged into one split group (lesion_id), so they can never be
      split between train and test."""
    labels_per_img = meta.groupby("image_id")["dx"].nunique()
    conflicting = set(labels_per_img[labels_per_img > 1].index)
    shared = meta[meta["image_id"].duplicated(keep=False) & ~meta["image_id"].isin(conflicting)]

    # union-find over case ids linked by a shared photo
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, grp in shared.groupby("image_id"):
        cases = list(grp["lesion_id"])
        for c in cases[1:]:
            parent[find(c)] = find(cases[0])
    meta = meta[~meta["image_id"].isin(conflicting)].copy()
    meta["lesion_id"] = meta["lesion_id"].map(lambda c: find(c) if c in parent else c)
    before = len(meta)
    meta = meta.drop_duplicates("image_id", keep="first")
    print(f"duplicates: dropped {len(conflicting)} photos with conflicting labels, "
          f"{before - len(meta)} repeated photos; merged cases sharing a photo into one split group")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="ml/configs/scin_groups.yaml")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--metadata-only", action="store_true")
    args = ap.parse_args()

    groups_cfg = yaml.safe_load(open(resolve(args.groups), encoding="utf-8"))
    meta = select_cases(groups_cfg)
    print(f"selected {meta['lesion_id'].nunique()} cases, {len(meta)} photos, "
          f"{meta['dx'].nunique()} condition groups", flush=True)

    if not args.metadata_only:
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        listing = list_bucket_md5()
        missing = [p for p in meta["bucket_path"] if p not in listing]
        if missing:
            print(f"warning: {len(missing)} photos listed in the CSV are not in the bucket (skipped)")
        todo = [(p, *listing[p]) for p in meta["bucket_path"] if p in listing]
        total_gb = sum(s for _, s, _ in todo) / 1e9
        print(f"verifying/downloading {len(todo)} photos ({total_gb:.2f} GB)", flush=True)
        results, done, t0 = {}, 0, time.time()
        with ThreadPoolExecutor(args.workers) as pool:
            futs = {pool.submit(download_one, *t): t[0] for t in todo}
            for fut in as_completed(futs):
                results[futs[fut]] = fut.result()
                done += 1
                if done % 50 == 0 or done == len(todo):
                    rate = done / max(time.time() - t0, 1e-6)
                    print(f"  {done}/{len(todo)} done, about {(len(todo) - done) / max(rate, 1e-6) / 60:.0f} min left",
                          flush=True)
        failed = [p for p, s in results.items() if s == "failed"]
        print(f"downloaded: {sum(s == 'downloaded' for s in results.values())}, "
              f"already ok: {sum(s == 'ok-cached' for s in results.values())}, failed: {len(failed)}")
        meta = meta[meta["bucket_path"].map(lambda p: results.get(p, "failed") != "failed")]

    meta = meta[meta["image_id"].map(lambda i: (IMG_DIR / f"{i}.png").exists())]
    meta = dedupe_shared_photos(meta)
    out = ROOT / "scin_metadata.csv"
    meta.drop(columns=["bucket_path"]).to_csv(out, index=False)
    print(f"wrote {out} with {len(meta)} photos from {meta['lesion_id'].nunique()} cases")
    print(meta.groupby("dx")["lesion_id"].nunique().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
