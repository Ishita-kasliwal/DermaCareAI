"""Print training progress per model run.   python -m ml.src.training_status"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    runs = sorted((ROOT / "ml" / "artifacts" / "runs").glob("*"))
    if not runs:
        print("No training runs yet.")
    for d in runs:
        f = d / "history.csv"
        try:
            h = pd.read_csv(f) if f.exists() else pd.DataFrame()
        except pd.errors.EmptyDataError:  # file created, first round not finished yet
            h = pd.DataFrame()
        if h.empty:
            print(f"{d.name}: round 1 in progress")
            continue
        last = h.iloc[-1]
        print(f"{d.name}: {len(h)} rounds done | latest val macro-F1 {last.val_macro_f1:.3f}, "
              f"val accuracy {last.val_accuracy:.3f} | best val macro-F1 {h.val_macro_f1.max():.3f}")
    latest = ROOT / "ml" / "artifacts" / "models" / "LATEST"
    if latest.exists():
        print(f"Exported model: {latest.read_text().strip()}")


if __name__ == "__main__":
    main()
