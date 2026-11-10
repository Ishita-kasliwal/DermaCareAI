"""Fixtures for ML tests.

The `synthetic_ham_layout` fixture writes RANDOM-NOISE images in the HAM10000 folder layout.
It exists ONLY to exercise code paths (I/O, splitting, training loop, export, inference).
Nothing trained on it is meaningful, and no metric from it is ever reported.
"""

import numpy as np
import pandas as pd
import pytest
from PIL import Image

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]


@pytest.fixture()
def synthetic_ham_layout(tmp_path):
    root = tmp_path / "HAM10000_SYNTHETIC_TEST_ONLY"
    img_dir = root / "HAM10000_images_part_1"
    img_dir.mkdir(parents=True)
    rng = np.random.default_rng(0)
    rows = []
    n = 0
    for c in CLASSES:
        for lesion in range(10):           # 10 lesions per class
            for _ in range(2):             # 2 images per lesion (like HAM10000 duplicates)
                image_id = f"SYN_{n:05d}"
                arr = rng.integers(0, 256, size=(90, 120, 3), dtype=np.uint8)
                Image.fromarray(arr).save(img_dir / f"{image_id}.jpg", quality=90)
                rows.append({"lesion_id": f"SYNL_{c}_{lesion}", "image_id": image_id, "dx": c,
                             "dx_type": "synthetic", "age": 50, "sex": "unknown",
                             "localization": "unknown"})
                n += 1
    pd.DataFrame(rows).to_csv(root / "HAM10000_metadata.csv", index=False)
    return root


def make_cfg(data_root, out_dir, image_size=64):
    return {
        "seed": 1,
        "deterministic": True,
        "output_dir": str(out_dir),
        "data": {"root": str(data_root), "metadata_csv": "HAM10000_metadata.csv",
                 "classes": CLASSES, "group_column": "lesion_id",
                 "split": {"train": 0.7, "val": 0.15, "test": 0.15}},
        "preprocess": {"image_size": image_size, "crop": "center_square"},
        "augmentation": {"enabled": True, "flip": "horizontal_and_vertical", "rotation": 0.5,
                         "zoom": 0.1, "contrast": 0.1, "brightness": 0.1},
        "imbalance": {"method": "class_weight", "power": 0.5},
        "training": {"batch_size": 8, "early_stopping_patience": 2, "monitor": "val_macro_f1"},
        "models": [
            {"name": "mobilenetv2", "weights": None, "dropout": 0.2,
             "stage1": {"epochs": 1, "learning_rate": 1e-3},
             "stage2": {"epochs": 1, "learning_rate": 1e-5, "unfreeze_last": 5}},
            {"name": "efficientnetb0", "weights": None, "dropout": 0.2,
             "stage1": {"epochs": 1, "learning_rate": 1e-3},
             "stage2": {"epochs": 1, "learning_rate": 1e-5, "unfreeze_last": 5}},
        ],
        "inference": {"confidence_threshold": 0.5},
    }
