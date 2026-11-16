"""Try the installed AI models on a few photos from the command line.

    .\\.venv\\Scripts\\python.exe scripts\\check_photos.py photo1.jpg photo2.png ...
    .\\.venv\\Scripts\\python.exe scripts\\check_photos.py --checker lesion mole.jpg

It uses exactly the same steps as the website: the same photo checks (OpenCV), the same preprocessing
(size, colour order RGB, normalisation inside the model) and the same model files and label order.
For each photo it prints the top 3 answers with a % and says "unclear" when the AI is less than 60% sure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED = {".jpg", ".jpeg", ".png"}
SURE = 0.60  # below this we never name one condition


def model_dir(domain: str) -> Path:
    """Folder of the newest exported model for a checker (same files the website registers)."""
    base = {"general": ROOT / "ml/artifacts/face/models", "lesion": ROOT / "ml/artifacts/models"}[domain]
    latest = (base / "LATEST").read_text(encoding="utf-8").strip()
    return base / latest


def check_one(path: Path, predictor, checker: str = "general") -> dict:
    from app.services.quality_service import assess
    from skinai_ml.classes import simple_name
    from skinai_ml.prediction import load_rgb_image

    if not path.exists():
        return {"photo": str(path), "error": "File not found. Please check the name and folder."}
    if path.suffix.lower() not in ALLOWED:
        return {"photo": str(path), "error": "Please use a JPG or PNG photo."}
    try:
        rgb = load_rgb_image(path)
    except Exception:  # noqa: BLE001
        return {"photo": str(path), "error": "This file couldn't be opened as a photo (it may be damaged)."}

    quality = assess(rgb)
    if checker != "lesion":  # face photos are fine for the rash checker (same rule as the website)
        quality.issues = [i for i in quality.issues if i["code"] != "face"]
    if quality.rejected:
        return {"photo": str(path), "error": quality.issues[0]["message"]}
    result = predictor.predict_array(rgb)
    top3 = [(simple_name(t["code"]), round(t["probability"] * 100, 1)) for t in result.top_k[:3]]
    if result.code == "unfamiliar":
        verdict = "This doesn't look like a close-up of a skin problem the AI knows."
    elif result.confidence < SURE:
        verdict = "Unclear: the AI is less than 60% sure. Please see a dermatologist if you're worried."
    else:
        verdict = f"Looks most like: {simple_name(result.code)} ({result.confidence:.0%} match)"
    return {"photo": path.name, "verdict": verdict, "top_3": top3,
            "photo_warnings": [i["message"] for i in quality.issues]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--checker", choices=["general", "lesion"], default="general",
                    help="general = rash checker (default), lesion = mole checker")
    args = ap.parse_args()

    from skinai_ml.prediction import SkinLesionPredictor

    folder = model_dir(args.checker)
    predictor = SkinLesionPredictor(folder)
    print(f"Model: {folder.name}  |  answers it knows: {', '.join(predictor.class_codes)}\n")
    for p in args.photos:
        print(json.dumps(check_one(Path(p), predictor, args.checker), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
