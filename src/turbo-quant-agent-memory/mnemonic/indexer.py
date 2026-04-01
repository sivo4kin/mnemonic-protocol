from __future__ import annotations

from typing import List, Optional

from .embedders import BaseEmbeddingProvider
from .math_utils import normalize
from .models import EmbeddingRecord, MemoryItem, QuantizedRecord
from .quantizer import CalibratedScalarQuantizer
from .store import MemoryStore


class MemoryIndexer:
    def __init__(self, store: MemoryStore, embedder: BaseEmbeddingProvider, quantizer: CalibratedScalarQuantizer):
        self.store = store
        self.embedder = embedder
        self.quantizer = quantizer

    def ingest_memory(
        self,
        memory_id: str,
        content: str,
        memory_type: str = "episodic",
        importance_score: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> None:
        tags = tags or []
        item = MemoryItem(memory_id, content, memory_type, importance_score, tags)
        self.store.put_item(item)
        full_embedding = self.embedder.embed_text(content)
        normalized, norm = normalize(full_embedding)
        self.store.put_embedding(
            EmbeddingRecord(
                memory_id=memory_id,
                embedding_model=self.embedder.model_name,
                embedding_dim=len(full_embedding),
                embedding_f32=full_embedding,
                embedding_norm=norm,
                normalized_f32=normalized,
            )
        )

    def rebuild_quantized_index(self) -> None:
        ids = self.store.memory_ids()
        if not ids:
            return
        normalized_vectors = [self.store.embeddings[mid].normalized_f32 for mid in ids]
        self.quantizer.fit(normalized_vectors)
        self.store.quantized = {}
        for memory_id in ids:
            emb = self.store.embeddings[memory_id]
            packed_codes, saturation_rate = self.quantizer.quantize_vector(emb.normalized_f32)
            self.store.put_quantized(
                QuantizedRecord(
                    memory_id=memory_id,
                    quant_bits=self.quantizer.bits,
                    quant_scheme="symmetric_uniform_per_dim_calibrated",
                    packed_codes=packed_codes,
                    embedding_dim=emb.embedding_dim,
                    saturation_rate=saturation_rate,
                )
            )
