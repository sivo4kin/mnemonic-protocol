from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MemoryItem:
    memory_id: str
    content: str
    memory_type: str = "episodic"
    importance_score: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class EmbeddingRecord:
    memory_id: str
    embedding_model: str
    embedding_dim: int
    embedding_f32: List[float]
    embedding_norm: float
    normalized_f32: List[float]


@dataclass
class QuantizedRecord:
    memory_id: str
    quant_bits: int
    quant_scheme: str
    packed_codes: bytes
    embedding_dim: int
    saturation_rate: float = 0.0


@dataclass
class SearchResult:
    memory_id: str
    approx_score: float
    exact_score: Optional[float] = None
    content: Optional[str] = None
