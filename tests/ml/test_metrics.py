import numpy as np

from ml.src.evaluate import compute_metrics


def test_metrics_hand_checked_example():
    classes = ["akiec", "bcc", "mel"]
    y_true = np.array([0, 0, 1, 1, 2, 2])
    # predictions: 0,1 | 1,1 | 2,0
    probs = np.array([
        [0.8, 0.1, 0.1], [0.2, 0.7, 0.1],
        [0.1, 0.8, 0.1], [0.1, 0.6, 0.3],
        [0.1, 0.1, 0.8], [0.5, 0.2, 0.3],
    ])
    m = compute_metrics(y_true, probs, classes)
    assert m["confusion_matrix"] == [[1, 1, 0], [0, 2, 0], [1, 0, 1]]
    assert np.isclose(m["accuracy"], 4 / 6)
    bcc = m["per_class"]["bcc"]
    assert np.isclose(bcc["recall_sensitivity"], 1.0)
    assert np.isclose(bcc["precision"], 2 / 3)
    assert np.isclose(bcc["specificity"], 3 / 4)   # TN=3, FP=1
    mel = m["per_class"]["mel"]
    assert np.isclose(mel["recall_sensitivity"], 0.5)
    assert np.isclose(mel["specificity"], 1.0)
    # all three are "malignant" codes here, so no benign negatives exist
    assert m["malignant_vs_benign"]["specificity"] is None
