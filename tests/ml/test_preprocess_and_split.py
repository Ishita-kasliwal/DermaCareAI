import numpy as np
import pytest

from ml.src.data_pipeline import build_augmenter, compute_class_weights
from ml.src.dataset import DatasetNotFoundError, get_or_create_splits, load_metadata, make_splits
from skinai_ml.preprocess import PreprocessConfig, preprocess_image
from tests.ml.conftest import make_cfg


def test_preprocess_shape_dtype_and_center_crop():
    img = np.zeros((450, 600, 3), dtype=np.uint8)
    img[:, :75] = 255  # left border that the center-square crop must remove
    out = preprocess_image(img, PreprocessConfig(image_size=224)).numpy()
    assert out.shape == (224, 224, 3) and out.dtype == np.uint8
    assert out.max() == 0


def test_preprocess_rejects_non_uint8():
    with pytest.raises(TypeError):
        preprocess_image(np.zeros((10, 10, 3), dtype=np.float32), PreprocessConfig())


def test_preprocess_config_roundtrip():
    cfg = PreprocessConfig(image_size=192, crop="none")
    assert PreprocessConfig.from_dict(cfg.to_dict()) == cfg


def test_missing_dataset_gives_download_help(tmp_path):
    cfg = make_cfg(tmp_path / "nope", tmp_path / "out")
    with pytest.raises(DatasetNotFoundError, match="10.7910/DVN/DBW86T"):
        load_metadata(cfg)


def test_grouped_split_has_no_lesion_leakage(synthetic_ham_layout, tmp_path):
    cfg = make_cfg(synthetic_ham_layout, tmp_path / "out")
    df = make_splits(load_metadata(cfg), cfg)
    assert set(df["split"]) == {"train", "val", "test"}
    assert (df.groupby("lesion_id")["split"].nunique() == 1).all()


def test_split_is_reproducible_and_persisted(synthetic_ham_layout, tmp_path):
    cfg = make_cfg(synthetic_ham_layout, tmp_path / "out")
    a = get_or_create_splits(cfg).sort_values("image_id")["split"].tolist()
    b = get_or_create_splits(cfg).sort_values("image_id")["split"].tolist()  # reads saved CSV
    c = make_splits(load_metadata(cfg), cfg).sort_values("image_id")["split"].tolist()
    assert a == b == c


def test_class_weights_favour_rare_classes():
    labels = np.array([0] * 90 + [1] * 10)
    w = compute_class_weights(labels, 2, power=1.0)
    assert w[1] > w[0]
    assert np.isclose((w[0] * 90 + w[1] * 10) / 100, 1.0)


def test_augmentation_varies_between_calls():
    cfg = make_cfg("x", "y")
    aug = build_augmenter(cfg, seed=0)
    x = np.random.default_rng(0).uniform(0, 255, (2, 32, 32, 3)).astype("float32")
    a1 = np.asarray(aug(x, training=True))
    a2 = np.asarray(aug(x, training=True))
    assert not np.allclose(a1, a2)
