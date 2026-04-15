from __future__ import annotations

from typing import Dict, List

from .models import EmbeddingRecord, MemoryItem, QuantizedRecord


class MemoryStore:
    def __init__(self):
        self.items: Dict[str, MemoryItem] = {}
        self.embeddings: Dict[str, EmbeddingRecord] = {}
        self.quantized: Dict[str, QuantizedRecord] = {}

    def put_item(self, item: MemoryItem) -> None:
        self.items[item.memory_id] = item

    def put_embedding(self, record: EmbeddingRecord) -> None:
        self.embeddings[record.memory_id] = record

    def put_quantized(self, record: QuantizedRecord) -> None:
        self.quantized[record.memory_id] = record

    def memory_ids(self) -> List[str]:
        return list(self.items.keys())
