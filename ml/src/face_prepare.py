"""Prepare the user-provided face/rash datasets into one labelled metadata file.

    python -m ml.src.face_prepare --acne <zip> --rash <zip>

- acne/redness zip: 30 people x 3 photos (front/left/right); classes acne, bags (eye bags), redness.
  Group = person, so all 3 photos of one person stay in the same split.
- rash zip: SkinRash/<condition>/<skin tone>/*.jpg; classes dermatitis, eczema, ringworm.
  No person IDs: each photo is its own group, and exact/near duplicates are merged into one group.
Extraction is path-safe (only image files, flattened names, no '..').
"""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import PurePosixPath

import numpy as np
import pandas as pd
from PIL import Image

from ml.src.utils import resolve

OUT = resolve("ml/data/raw/FACE")
IMG = OUT / "images"
EXTS = (".jpg", ".jpeg", ".png")


def _dhash(img: Image.Image, size: int = 16) -> int:
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def _save(data: bytes, name: str) -> tuple[str, int]:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    dest = IMG / f"{name}.jpg"
    img.save(dest, "JPEG", quality=92)
    return dest.stem, _dhash(img)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--acne", required=True)
    ap.add_argument("--rash", required=True)
    args = ap.parse_args()
    IMG.mkdir(parents=True, exist_ok=True)
    rows = []

    with zipfile.ZipFile(args.acne) as z:
        for n in z.namelist():
            p = PurePosixPath(n)
            if p.suffix.lower() not in EXTS or ".." in p.parts:
                continue
            # files/<class>/<person>/<view>.jpg
            cls, person, view = p.parts[-3], p.parts[-2], p.stem
            image_id, h = _save(z.read(n), f"acne_{cls}_{person}_{view}")
            rows.append({"image_id": image_id, "lesion_id": f"person_{person}", "dx": cls if cls != "bags" else "eye_bags",
                         "source": "acne_redness", "skin_tone": None, "view": view, "hash": h})

    with zipfile.ZipFile(args.rash) as z:
        for i, n in enumerate(sorted(z.namelist())):
            p = PurePosixPath(n)
            if p.suffix.lower() not in EXTS or ".." in p.parts:
                continue
            cls = p.parts[-3].lower()
            tone = p.parts[-2].replace("Balck", "Black")
            image_id, h = _save(z.read(n), f"rash_{cls}_{tone.lower()}_{i:04d}")
            rows.append({"image_id": image_id, "lesion_id": f"img_{image_id}", "dx": cls, "source": "skin_rash",
                         "skin_tone": tone, "view": None, "hash": h})

    df = pd.DataFrame(rows)
    # near-duplicate detection (Hamming distance <= 10 of 256 bits) -> same group; conflicting labels dropped
    hashes = df["hash"].tolist()
    parent = list(range(len(df)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    dup_pairs = 0
    for a in range(len(hashes)):
        for b in range(a + 1, len(hashes)):
            if bin(hashes[a] ^ hashes[b]).count("1") <= 10:
                parent[find(b)] = find(a)
                dup_pairs += 1
    df["cluster"] = [find(i) for i in range(len(df))]
    conflicting = df.groupby("cluster")["dx"].nunique()
    conflicting = set(conflicting[conflicting > 1].index)
    root_group = df.groupby("cluster")["lesion_id"].first()
    df["lesion_id"] = df["cluster"].map(root_group)
    before = len(df)
    df = df[~df["cluster"].isin(conflicting)]
    print(f"near-duplicate pairs: {dup_pairs}; photos dropped for conflicting labels: {before - len(df)}")
    df.drop(columns=["hash", "cluster"]).to_csv(OUT / "face_metadata.csv", index=False)
    print(df.groupby("dx").agg(photos=("image_id", "count"), groups=("lesion_id", "nunique")).to_string())


if __name__ == "__main__":
    main()
