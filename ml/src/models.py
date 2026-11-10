"""Transfer-learning model builders.

All models take float32 RGB in [0, 255]; architecture-specific normalisation is
inside the model, so the exported model and preprocess_config.json are self-describing.
"""

from __future__ import annotations

import keras

SUPPORTED = ("mobilenetv2", "efficientnetb0")


def build_model(name: str, num_classes: int, image_size: int, weights: str | None = "imagenet",
                dropout: float = 0.3) -> tuple[keras.Model, keras.Model]:
    """Returns (model, backbone)."""
    name = name.lower()
    if weights in ("none", "None", ""):
        weights = None
    shape = (image_size, image_size, 3)
    inputs = keras.Input(shape=shape, dtype="float32", name="image")

    if name == "mobilenetv2":
        x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0, name="to_minus1_1")(inputs)
        backbone = keras.applications.MobileNetV2(
            input_shape=shape, include_top=False, weights=weights, pooling="avg"
        )
    elif name == "efficientnetb0":
        x = inputs  # EfficientNet (Keras) contains its own Rescaling + Normalization layers
        backbone = keras.applications.EfficientNetB0(
            input_shape=shape, include_top=False, weights=weights, pooling="avg"
        )
    else:
        raise ValueError(f"unknown model {name!r}; supported: {SUPPORTED}")

    backbone.trainable = False
    x = backbone(x, training=False)  # keep BatchNorm in inference mode during fine-tuning
    x = keras.layers.Dropout(dropout, name="head_dropout")(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", dtype="float32", name="probs")(x)
    model = keras.Model(inputs, outputs, name=f"skin_{name}")
    return model, backbone


def unfreeze_top(backbone: keras.Model, n_layers: int) -> int:
    """Unfreeze the last n layers of the backbone, keeping BatchNormalization frozen."""
    backbone.trainable = True
    cutoff = max(0, len(backbone.layers) - int(n_layers))
    trainable = 0
    for i, layer in enumerate(backbone.layers):
        is_bn = isinstance(layer, keras.layers.BatchNormalization)
        layer.trainable = (i >= cutoff) and not is_bn
        trainable += int(layer.trainable)
    return trainable


def compile_model(model: keras.Model, num_classes: int, lr: float, label_smoothing: float = 0.0):
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr),
        loss=keras.losses.CategoricalCrossentropy(label_smoothing=label_smoothing),
        metrics=[
            keras.metrics.CategoricalAccuracy(name="accuracy"),
            keras.metrics.F1Score(average="macro", threshold=None, name="macro_f1"),
            keras.metrics.AUC(name="auc", multi_label=False),
        ],
    )
