"""Cross-platform HAM10000 downloader (used on Colab/Kaggle/Linux; Windows can use the .ps1 too).

    python -m ml.src.download_ham10000

Downloads from the official Harvard Dataverse record doi:10.7910/DVN/DBW86T (CC BY-NC 4.0), resumes after
connection drops, verifies MD5, extracts, and checks metadata rows == JPEG count.
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
import zipfile

from ml.src.utils import resolve

API = "https://dataverse.harvard.edu/api/access/datafile"
FILES = [
    (3172585, "HAM10000_images_part_1.zip", "4639bfa73ab251610530a97c898e6e46", "HAM10000_images_part_1"),
    (3172584, "HAM10000_images_part_2.zip", "da43d6cc50f6613013be07e8986b384b", "HAM10000_images_part_2"),
]
META_ID = 4338392


def md5(path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, dest, attempts: int = 200) -> None:
    """Download with HTTP Range resume; retries on any network error."""
    for attempt in range(1, attempts + 1):
        have = dest.stat().st_size if dest.exists() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                mode = "ab" if have and r.status == 206 else "wb"
                with open(dest, mode) as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            return
        except Exception as e:  # noqa: BLE001 - network errors of all kinds: resume
            print(f"  connection problem ({e.__class__.__name__}); resuming, attempt {attempt}", flush=True)
            time.sleep(min(60, 5 * attempt))
    raise RuntimeError(f"download failed: {url}")


def main() -> None:
    root = resolve("ml/data/raw/HAM10000")
    dl = root / "_downloads"
    dl.mkdir(parents=True, exist_ok=True)
    print("HAM10000, CC BY-NC 4.0 (non-commercial, attribution). See docs/DATASETS.md", flush=True)
    for file_id, name, expected, folder in FILES:
        zpath = dl / name
        if not (zpath.exists() and md5(zpath) == expected):
            print(f"downloading {name} ...", flush=True)
            fetch(f"{API}/{file_id}", zpath)
            if md5(zpath) != expected:
                zpath.unlink()
                raise RuntimeError(f"MD5 mismatch for {name}; deleted, please re-run")
        print(f"verified {name}", flush=True)
        out = root / folder
        if not any(out.glob("*.jpg")):
            out.mkdir(exist_ok=True)
            with zipfile.ZipFile(zpath) as z:
                for member in z.infolist():
                    if member.filename.lower().endswith(".jpg"):
                        member.filename = member.filename.split("/")[-1]  # flatten, no path traversal
                        z.extract(member, out)
    meta = root / "HAM10000_metadata.csv"
    if not meta.exists():
        fetch(f"{API}/{META_ID}?format=original", meta)
    rows = sum(1 for _ in open(meta, encoding="utf-8")) - 1
    jpgs = len(list(root.rglob("*.jpg")))
    print(f"metadata rows: {rows}, JPEG files: {jpgs}")
    if rows != jpgs:
        raise SystemExit("row/file count mismatch; re-run to repair")


if __name__ == "__main__":
    main()
