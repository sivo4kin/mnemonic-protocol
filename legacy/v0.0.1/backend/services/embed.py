"""Embedding service — fastembed (local ONNX) with hash fallback."""
from __future__ import annotations

import hashlib
import struct
import math
from typing import Optional

import numpy as np

from ..config import settings

_model: Optional[object] = None
_use_fastembed: bool = False
_dim: int = 384


def _init_model() -> None:
    global _model, _use_fastembed, _dim
    if _model is not None:
        return
    try:
        from fastembed import TextEmbedding
        _model = TextEmbedding(settings.EMBED_MODEL)
        _use_fastembed = True
        # Probe dimension
        sample = list(_model.embed(["test"]))[0]
        _dim = len(sample)
    except Exception:
        _model = "hash_fallback"
        _use_fastembed = False
        _dim = 384


def get_dim() -> int:
    _init_model()
    return _dim


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns f32 vector."""
    _init_model()
    if _use_fastembed:
        return list(_model.embed([text]))[0].tolist()
    return _hash_embed(text)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts."""
    _init_model()
    if _use_fastembed:
        return [v.tolist() for v in _model.embed(texts)]
    return [_hash_embed(t) for t in texts]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = float(np.dot(va, vb))
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _hash_embed(text: str) -> list[float]:
    """Deterministic hash-based embedder (fallback when fastembed unavailable)."""
    vec = [0.0] * _dim
    for chunk in range(_dim // 8 + 1):
        h = hashlib.sha256(f"{text}:{chunk}".encode()).digest()
        for j, offset in enumerate(range(0, 32, 4)):
            idx = chunk * 8 + j
            if idx >= _dim:
                break
            raw = struct.unpack_from("<I", h, offset)[0]
            vec[idx] = (raw / 0xFFFFFFFF) * 2.0 - 1.0
    # L2-normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec
