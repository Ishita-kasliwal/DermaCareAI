"""Download the three approved Roboflow Universe datasets (all CC BY 4.0) for the rash checker.

    python -m ml.src.roboflow_download            # needs ROBOFLOW_API_KEY in .env

Datasets (approved by the project owner on 2026-11-16):
  skin_analysis  image-classification-q4nkn/skin-analysis-oue1i   Acne, Dark Circles, Pigmentation, Pores, Redness, Wrinkles
  skin_type      neeta/oily-zkvaz                                  dry, oily, normal, combination
  wounds         clinicvision/basic-wound-classify-mpoys           abrasion, bruise, burn, laceration, normal skin
  acne_types     anum-wq0lb/acneclassification                     acne-comedonica, -conglobata, -papulopustulosa
  acne_types2    anum-wq0lb/acneclassification2                    same 3 acne types (larger version)

The key is read from the environment / .env and is never printed or saved anywhere else. Each export is
downloaded as Roboflow's "folder" classification format and unzipped (path-safely) into
ml/data/raw/ROBOFLOW/<name>/. Nothing here is committed to git (ml/data is git-ignored).
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from ml.src.utils import resolve

DATASETS = {
    "skin_analysis": ("image-classification-q4nkn", "skin-analysis-oue1i"),
    "skin_type": ("neeta", "oily-zkvaz"),
    "wounds": ("clinicvision", "basic-wound-classify-mpoys"),
    # acne types (approved 2026-11-16 after a forehead-acne photo came back as ringworm)
    "acne_types": ("anum-wq0lb", "acneclassification"),
    "acne_types2": ("anum-wq0lb", "acneclassification2"),
}
OUT = resolve("ml/data/raw/ROBOFLOW")
API = "https://api.roboflow.com"


def api_key() -> str:
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        env = resolve(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ROBOFLOW_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("ROBOFLOW_API_KEY is empty. Add your private Roboflow API key to .env, then run this again.")
    return key


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "dermacareai-dataset-download"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed https host
        return json.loads(r.read().decode("utf-8"))


def latest_version(ws: str, project: str, key: str) -> int:
    info = get_json(f"{API}/{ws}/{project}?" + urllib.parse.urlencode({"api_key": key}))
    versions = info.get("versions") or []
    if not versions:
        raise RuntimeError(f"{ws}/{project} has no published versions")
    return max(int(str(v["id"]).rsplit("/", 1)[-1]) for v in versions)


def export_link(ws: str, project: str, version: int, key: str) -> str:
    url = f"{API}/{ws}/{project}/{version}/folder?" + urllib.parse.urlencode({"api_key": key})
    for _ in range(60):  # Roboflow may need a moment to prepare a fresh export
        data = get_json(url)
        link = (data.get("export") or {}).get("link")
        if link:
            return link
        time.sleep(5)
    raise RuntimeError(f"export of {ws}/{project} v{version} was not ready in time")


def safe_extract(blob: bytes, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    n = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for m in z.infolist():
            target = (root / m.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"unsafe path in zip: {m.filename}")
            if m.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(m))
            n += 1
    return n


def main() -> None:
    key = api_key()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (ws, project) in DATASETS.items():
        dest = OUT / name
        if dest.exists() and any(dest.rglob("*.jpg")):
            print(f"{name}: already downloaded, skipping")
            continue
        version = latest_version(ws, project, key)
        print(f"{name}: preparing export of {ws}/{project} v{version} ...", flush=True)
        link = export_link(ws, project, version, key)
        with urllib.request.urlopen(link, timeout=600) as r:  # noqa: S310 - link returned by Roboflow
            blob = r.read()
        files = safe_extract(blob, dest)
        (dest / "SOURCE.json").write_text(json.dumps({
            "workspace": ws, "project": project, "version": version, "licence": "CC BY 4.0",
            "url": f"https://universe.roboflow.com/{ws}/{project}", "downloaded": time.strftime("%Y-%m-%d"),
        }, indent=2), encoding="utf-8")
        print(f"{name}: {files} files, {len(blob) / 1e6:.1f} MB")
    for name in DATASETS:
        d = OUT / name
        classes: dict[str, int] = {}
        for f in d.rglob("*"):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                classes[f.parent.name] = classes.get(f.parent.name, 0) + 1
        print(f"{name}: {dict(sorted(classes.items()))}")


if __name__ == "__main__":
    main()
