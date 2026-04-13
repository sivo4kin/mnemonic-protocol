"""Embedding service — fastembed (local ONNX) with deterministic hash fallback."""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Optional

import numpy as np

from .config import config

_model: Optional[object] = None
_use_fastembed: bool = False
_dim: int = 384


def _init() -> None:
    global _model, _use_fastembed, _dim
    if _model is not None:
        return
    try:
        from fastembed import TextEmbedding
        _model = TextEmbedding(config.EMBED_MODEL)
        _use_fastembed = True
        sample = list(_model.embed(["test"]))[0]
        _dim = len(sample)
    except Exception:
        _model = "hash_fallback"
        _use_fastembed = False
        _dim = 384


def get_dim() -> int:
    _init()
    return _dim


def embed_text(text: str) -> list[float]:
    _init()
    if _use_fastembed:
        return list(_model.embed([text]))[0].tolist()
    return _hash_embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = float(np.dot(va, vb))
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * _dim
    for chunk in range(_dim // 8 + 1):
        h = hashlib.sha256(f"{text}:{chunk}".encode()).digest()
        for j, offset in enumerate(range(0, 32, 4)):
            idx = chunk * 8 + j
            if idx >= _dim:
                break
            raw = struct.unpack_from("<I", h, offset)[0]
            vec[idx] = (raw / 0xFFFFFFFF) * 2.0 - 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec
