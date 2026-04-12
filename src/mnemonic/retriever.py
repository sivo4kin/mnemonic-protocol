from __future__ import annotations

import heapq
from typing import List, Tuple

from .embedders import BaseEmbeddingProvider
from .math_utils import dot, normalize
from .models import SearchResult
from .quantizer import CalibratedScalarQuantizer, TurboQuantAdapter
from .indexer import Quantizer
from .store import MemoryStore


class MemoryRetriever:
    def __init__(self, store: MemoryStore, embedder: BaseEmbeddingProvider, quantizer: Quantizer):
        self.store = store
        self.embedder = embedder
        self.quantizer = quantizer

    def retrieve(self, query_text: str, k: int = 5, n_candidates: int = 10) -> List[SearchResult]:
        query_vec = self.embedder.embed_text(query_text)
        query_normed, _ = normalize(query_vec)
        candidates = self._compressed_candidate_search(query_normed, n_candidates)
        return self._exact_rerank(query_normed, candidates, k)

    def compressed_candidates(self, query_text: str, n_candidates: int = 10) -> List[SearchResult]:
        query_vec = self.embedder.embed_text(query_text)
        query_normed, _ = normalize(query_vec)
        return self._compressed_candidate_search(query_normed, n_candidates)

    def exact_search(self, query_text: str, k: int = 5) -> List[SearchResult]:
        query_vec = self.embedder.embed_text(query_text)
        query_normed, _ = normalize(query_vec)
        scored = []
        for memory_id in self.store.memory_ids():
            emb = self.store.embeddings[memory_id]
            item = self.store.items[memory_id]
            score = dot(query_normed, emb.normalized_f32)
            scored.append(SearchResult(memory_id=memory_id, approx_score=score, exact_score=score, content=item.content))
        scored.sort(key=lambda r: r.exact_score if r.exact_score is not None else -1e9, reverse=True)
        return scored[:k]

    def _compressed_candidate_search(self, query_normed: List[float], n_candidates: int) -> List[SearchResult]:
        heap: List[Tuple[float, str]] = []
        for memory_id in self.store.memory_ids():
            qrec = self.store.quantized[memory_id]
            approx_score = self.quantizer.score_query_against_codes(query_normed, qrec.packed_codes, qrec.embedding_dim)
            if len(heap) < n_candidates:
                heapq.heappush(heap, (approx_score, memory_id))
            elif approx_score > heap[0][0]:
                heapq.heapreplace(heap, (approx_score, memory_id))
        ranked = sorted(heap, reverse=True)
        return [SearchResult(memory_id=mid, approx_score=score, content=self.store.items[mid].content) for score, mid in ranked]

    def _exact_rerank(self, query_normed: List[float], candidates: List[SearchResult], k: int) -> List[SearchResult]:
        reranked: List[SearchResult] = []
        for cand in candidates:
            emb = self.store.embeddings[cand.memory_id]
            item = self.store.items[cand.memory_id]
            exact_score = dot(query_normed, emb.normalized_f32)
            reranked.append(SearchResult(cand.memory_id, cand.approx_score, exact_score, item.content))
        reranked.sort(key=lambda r: r.exact_score if r.exact_score is not None else -1e9, reverse=True)
        return reranked[:k]
