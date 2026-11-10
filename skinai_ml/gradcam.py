"""Grad-CAM heatmaps for the exported Keras models (nested backbone or flat models)."""

from __future__ import annotations

import cv2
import keras
import numpy as np
import tensorflow as tf


def _is_4d(layer) -> bool:
    try:
        return len(layer.output.shape) == 4
    except (AttributeError, ValueError):
        return False


def _locate_conv(model: keras.Model):
    """Returns (backbone_or_None, last_4d_layer)."""
    for layer in reversed(model.layers):
        if isinstance(layer, keras.Model):
            for inner in reversed(layer.layers):
                if _is_4d(inner):
                    return layer, inner
    for layer in reversed(model.layers):
        if _is_4d(layer) and not isinstance(layer, keras.layers.InputLayer):
            return None, layer
    raise ValueError("no convolutional feature map found for Grad-CAM")


def compute_heatmap(model: keras.Model, x: np.ndarray | tf.Tensor, class_index: int) -> np.ndarray:
    """x: float32 (1, S, S, 3). Returns heatmap in [0, 1], shape (S, S)."""
    x = tf.convert_to_tensor(x, dtype=tf.float32)
    backbone, conv_layer = _locate_conv(model)

    with tf.GradientTape() as tape:
        if backbone is None:
            grad_model = keras.Model(model.inputs, [conv_layer.output, model.output])
            conv_out, preds = grad_model(x, training=False)
        else:
            inner = keras.Model(backbone.inputs, [conv_layer.output, backbone.output])
            h = x
            conv_out = None
            for layer in model.layers:
                if isinstance(layer, keras.layers.InputLayer):
                    continue
                if layer is backbone:
                    conv_out, h = inner(h, training=False)
                else:
                    h = layer(h, training=False)
            preds = h
        score = preds[:, class_index]

    grads = tape.gradient(score, conv_out)
    if grads is None:
        raise ValueError("gradient unavailable for Grad-CAM")
    weights = tf.reduce_mean(grads, axis=(1, 2))
    cam = tf.nn.relu(tf.reduce_sum(conv_out * weights[:, None, None, :], axis=-1))[0].numpy()
    if cam.max() > 0:
        cam = cam / cam.max()
    size = int(x.shape[1])
    return cv2.resize(cam.astype(np.float32), (size, size), interpolation=cv2.INTER_LINEAR)


def overlay(rgb_uint8: np.ndarray, heatmap: np.ndarray, alpha: float = 0.40) -> np.ndarray:
    """Blend a heatmap onto the (preprocessed) image; returns uint8 RGB."""
    colour = cv2.applyColorMap((heatmap * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    colour = cv2.cvtColor(colour, cv2.COLOR_BGR2RGB)
    return cv2.addWeighted(rgb_uint8, 1 - alpha, colour, alpha, 0)
