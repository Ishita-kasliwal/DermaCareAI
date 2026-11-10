"""End-to-end smoke test on SYNTHETIC noise images (code paths only; results are meaningless)."""

import json

import numpy as np
import pytest

from ml.src.run_pipeline import run
from skinai_ml.prediction import ModelIntegrityError, SkinLesionPredictor
from tests.ml.conftest import CLASSES, make_cfg


@pytest.mark.slow
def test_full_pipeline_runs_and_exports(synthetic_ham_layout, tmp_path):
    cfg = make_cfg(synthetic_ham_layout, tmp_path / "artifacts")
    summary = run(cfg, skip_eda=False)

    assert summary["selected"] in {"mobilenetv2", "efficientnetb0"}
    assert len(summary["comparison"]) == 2
    export_dir = tmp_path / "artifacts" / "models" / (tmp_path / "artifacts" / "models" / "LATEST").read_text()
    for f in ("model.keras", "labels.json", "preprocess_config.json", "metrics.json",
              "manifest.json", "MODEL_CARD.md"):
        assert (export_dir / f).exists(), f
    assert (tmp_path / "artifacts" / "reports" / "eda" / "sample_images.png").exists()

    metrics = json.loads((export_dir / "metrics.json").read_text())
    assert set(metrics) == {"validation", "test"}
    assert "specificity" in metrics["test"]["per_class"]["mel"]

    # reusable predictor
    predictor = SkinLesionPredictor(export_dir)
    img = synthetic_ham_layout / "HAM10000_images_part_1" / "SYN_00000.jpg"
    res = predictor.predict(img)
    assert res.code in CLASSES
    assert np.isclose(sum(res.probabilities.values()), 1.0, atol=1e-4)
    assert res.status in {"confident", "inconclusive"}
    assert predictor.predict(img.read_bytes()).probabilities == res.probabilities  # deterministic

    # tampered model must be refused
    with open(export_dir / "model.keras", "ab") as f:
        f.write(b"tamper")
    with pytest.raises(ModelIntegrityError):
        SkinLesionPredictor(export_dir).predict(img)
