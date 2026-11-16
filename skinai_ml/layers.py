"""Custom Keras layers used inside exported models. Imported before a model is loaded.

SkinPhotoGate: turns "which condition?" probabilities into an answer that can also say
"this doesn't look like a skin problem the AI knows".

It compares the photo's CLIP embedding with fixed text descriptions ("a close-up photo of a red itchy
skin rash", "a selfie of a person", ...). The first `n_good` descriptions are skin problems the checker
knows; the rest are things it should not judge. p_skin = sigmoid(logsumexp(good) - logsumexp(other) + bias).
Output: [p_skin * condition probabilities..., 1 - p_skin]  (still sums to 1).
"""

from __future__ import annotations

import keras
from keras import ops


@keras.saving.register_keras_serializable(package="skinai")
class SkinPhotoGate(keras.layers.Layer):
    def __init__(self, n_texts: int, n_good: int, dim: int, temperature: float = 100.0, bias: float = 0.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.n_texts, self.n_good, self.dim = int(n_texts), int(n_good), int(dim)
        self.temperature, self.bias = float(temperature), float(bias)
        self.text_embeddings = self.add_weight(name="text_embeddings", shape=(self.n_texts, self.dim),
                                               initializer="zeros", trainable=False)

    def call(self, inputs):
        emb, probs = inputs
        emb = emb / ops.maximum(ops.norm(emb, axis=-1, keepdims=True), 1e-12)
        logits = self.temperature * ops.matmul(emb, ops.transpose(self.text_embeddings))
        good = ops.logsumexp(logits[:, : self.n_good], axis=-1, keepdims=True)
        other = ops.logsumexp(logits[:, self.n_good:], axis=-1, keepdims=True)
        p_skin = ops.sigmoid(good - other + self.bias)
        return ops.concatenate([probs * p_skin, 1.0 - p_skin], axis=-1)

    def get_config(self):
        cfg = super().get_config()
        cfg.update(n_texts=self.n_texts, n_good=self.n_good, dim=self.dim, temperature=self.temperature,
                   bias=self.bias)
        return cfg
