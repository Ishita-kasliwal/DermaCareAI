"""Accuracy upgrades: test-time augmentation, class-weight boosts, EfficientNetB3, GPU configs."""

import json

import numpy as np
import pytest

from ml.src.data_pipeline import compute_class_weights
from ml.src.models import build_model
from ml.src.utils import load_config
from skinai_ml.preprocess import PreprocessConfig, tta_views


def test_preprocess_config_tta_roundtrip_and_validation():
    cfg = PreprocessConfig(image_size=300, tta=("hflip", "vflip"))
    assert PreprocessConfig.from_dict(cfg.to_dict()) == cfg
    assert PreprocessConfig.from_dict({"image_size": 224}).tta == ()  # old exported models: no TTA
    with pytest.raises(ValueError):
        PreprocessConfig(tta=("rotate",))


def test_tta_views_are_flips():
    x = np.arange(2 * 4 * 4 * 3, dtype="float32").reshape(2, 4, 4, 3)
    views = [np.asarray(v) for v in tta_views(x, ("hflip", "vflip"))]
    assert len(views) == 3
    assert np.array_equal(views[1], x[:, :, ::-1, :]) and np.array_equal(views[2], x[:, ::-1, :, :])


def test_boost_increases_relative_weight_and_keeps_mean_one():
    labels = np.array([0] * 80 + [1] * 10 + [2] * 10)
    base = compute_class_weights(labels, 3, power=0.5)
    boosted = compute_class_weights(labels, 3, power=0.5, boost={1: 2.0})
    assert boosted[1] / boosted[2] == pytest.approx(2 * base[1] / base[2], rel=1e-4)
    assert (boosted[0] * 80 + boosted[1] * 10 + boosted[2] * 10) / 100 == pytest.approx(1.0, rel=1e-4)


def test_efficientnetb3_builds():
    model, backbone = build_model("efficientnetb3", 7, 64, weights=None)
    assert model.output_shape == (None, 7) and not backbone.trainable


@pytest.mark.parametrize("path", ["ml/configs/train_gpu.yaml", "ml/configs/train_scin_gpu.yaml"])
def test_gpu_configs_are_consistent(path):
    cfg = load_config(path)
    PreprocessConfig(image_size=cfg["preprocess"]["image_size"], tta=tuple(cfg["preprocess"]["tta"]))
    assert set(cfg["imbalance"].get("boost", {})) <= set(cfg["data"]["classes"])
    assert {m["name"] for m in cfg["models"]} <= {"mobilenetv2", "efficientnetb0", "efficientnetb3"}


def test_predictor_tta_averages_views(tmp_path):
    """The deployed predictor must average original + flipped views exactly like evaluation does."""
    import keras

    from skinai_ml.prediction import SkinLesionPredictor
    from tests.conftest import CLASSES, _export_tiny_model

    d = _export_tiny_model(tmp_path / "m", "tta-test", favour=None)
    pc = json.loads((d / "preprocess_config.json").read_text())
    pc["tta"] = ["hflip", "vflip"]
    (d / "preprocess_config.json").write_text(json.dumps(pc))
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (120, 90, 3), dtype=np.uint8)
    pred = SkinLesionPredictor(d)
    got = np.array([pred.predict_array(img).probabilities[c] for c in CLASSES])

    from skinai_ml.preprocess import preprocess_image, to_model_input
    model = keras.models.load_model(d / "model.keras", compile=False)
    x = np.asarray(to_model_input(preprocess_image(img, pred.preprocess_cfg)))[None]
    manual = np.mean([model(v)[0] for v in (x, x[:, :, ::-1], x[:, ::-1])], axis=0)
    assert np.allclose(got, manual, atol=1e-5)
