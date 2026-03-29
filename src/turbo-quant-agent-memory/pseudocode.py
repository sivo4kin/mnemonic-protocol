"""
Runnable minimal prototype for a compressed agent memory MVP.

Design:
- full-precision normalized vectors are kept for exact rerank
- compressed vectors are used for candidate generation
- exact rerank is the correction layer

No external APIs. No dependencies beyond Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import argparse
import hashlib
import heapq
import math
import random
import sys


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------

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
    clip_alpha: float
    quant_scheme: str
    packed_codes: bytes
    dequant_scale: float
    embedding_dim: int
    saturation_rate: float = 0.0


@dataclass
class SearchResult:
    memory_id: str
    approx_score: float
    exact_score: Optional[float] = None
    content: Optional[str] = None


# -----------------------------------------------------------------------------
# Math helpers
# -----------------------------------------------------------------------------

def dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def l2_norm(vec: List[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def normalize(vec: List[float]) -> Tuple[List[float], float]:
    norm = l2_norm(vec)
    if norm == 0.0:
        return [0.0 for _ in vec], 0.0
    return [x / norm for x in vec], norm


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# -----------------------------------------------------------------------------
# Mock embedding provider
# -----------------------------------------------------------------------------

class MockEmbeddingProvider:
    """
    Deterministic offline embedder.

    It mixes:
    - hashed token buckets
    - a few simple lexical signals

    Good enough for a local MVP demo and benchmark.
    """

    def __init__(self, model_name: str = "mock-hash-embedder", dim: int = 256):
        self.model_name = model_name
        self.dim = dim

    def embed_text(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        lowered = text.lower()
        tokens = self._tokenize(lowered)

        if not tokens:
            return vec

        # hashed bag-of-words with signed updates
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx1 = int.from_bytes(digest[0:4], "big") % self.dim
            idx2 = int.from_bytes(digest[4:8], "big") % self.dim
            sign1 = 1.0 if digest[8] % 2 == 0 else -1.0
            sign2 = 1.0 if digest[9] % 2 == 0 else -1.0
            strength = 1.0 + (len(token) % 5) * 0.05
            vec[idx1] += sign1 * strength
            vec[idx2] += sign2 * 0.6 * strength

        # simple lexical features in the tail
        vec[0] += len(tokens) / 20.0
        vec[1] += sum(c.isdigit() for c in lowered) / 10.0
        vec[2] += lowered.count("blockchain") * 0.8
        vec[3] += lowered.count("agent") * 0.8
        vec[4] += lowered.count("memory") * 0.8
        vec[5] += lowered.count("quant") * 0.8
        vec[6] += lowered.count("retrieval") * 0.8
        vec[7] += lowered.count("cache") * 0.8

        return vec

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        cleaned = []
        token = []
        for ch in text:
            if ch.isalnum() or ch in {"-", "_"}:
                token.append(ch)
            else:
                if token:
                    cleaned.append("".join(token))
                    token = []
        if token:
            cleaned.append("".join(token))
        return cleaned


# -----------------------------------------------------------------------------
# Quantizer
# -----------------------------------------------------------------------------

class ScalarQuantizer:
    def __init__(self, bits: int = 8, clip_alpha: float = 0.25):
        if bits not in (4, 8):
            raise ValueError("Only 4-bit and 8-bit modes are supported")
        self.bits = bits
        self.clip_alpha = clip_alpha
        self.levels = 2 ** bits
        self.max_int = self.levels - 1
        self.step = (2.0 * clip_alpha) / self.max_int

    def quantize_vector(self, vec: List[float]) -> Tuple[bytes, float, float]:
        codes: List[int] = []
        saturated = 0

        for x in vec:
            x_clipped = clip(x, -self.clip_alpha, self.clip_alpha)
            if x_clipped != x:
                saturated += 1
            q = round((x_clipped + self.clip_alpha) / self.step)
            q = max(0, min(self.max_int, int(q)))
            codes.append(q)

        return self.pack_codes(codes), self.step, saturated / max(1, len(vec))

    def dequantize_vector(self, packed_codes: bytes, dim: int) -> List[float]:
        codes = self.unpack_codes(packed_codes, dim)
        return [-self.clip_alpha + q * self.step for q in codes]

    def pack_codes(self, codes: List[int]) -> bytes:
        if self.bits == 8:
            return bytes(codes)

        packed = bytearray()
        for i in range(0, len(codes), 2):
            a = codes[i]
            b = codes[i + 1] if i + 1 < len(codes) else 0
            packed.append((a << 4) | b)
        return bytes(packed)

    def unpack_codes(self, packed: bytes, dim: int) -> List[int]:
        if self.bits == 8:
            return list(packed[:dim])

        out: List[int] = []
        for byte in packed:
            out.append((byte >> 4) & 0x0F)
            out.append(byte & 0x0F)
            if len(out) >= dim:
                break
        return out[:dim]


# -----------------------------------------------------------------------------
# Stores
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Indexer
# -----------------------------------------------------------------------------

class MemoryIndexer:
    def __init__(self, store: MemoryStore, embedder: MockEmbeddingProvider, quantizer: ScalarQuantizer):
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

        packed_codes, scale, saturation_rate = self.quantizer.quantize_vector(normalized)
        self.store.put_quantized(
            QuantizedRecord(
                memory_id=memory_id,
                quant_bits=self.quantizer.bits,
                clip_alpha=self.quantizer.clip_alpha,
                quant_scheme="symmetric_uniform_global",
                packed_codes=packed_codes,
                dequant_scale=scale,
                embedding_dim=len(normalized),
                saturation_rate=saturation_rate,
            )
        )


# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------

class MemoryRetriever:
    def __init__(self, store: MemoryStore, embedder: MockEmbeddingProvider, quantizer: ScalarQuantizer):
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
            approx_vec = self.quantizer.dequantize_vector(qrec.packed_codes, qrec.embedding_dim)
            approx_score = dot(query_normed, approx_vec)
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
            reranked.append(
                SearchResult(
                    memory_id=cand.memory_id,
                    approx_score=cand.approx_score,
                    exact_score=exact_score,
                    content=item.content,
                )
            )
        reranked.sort(key=lambda r: r.exact_score if r.exact_score is not None else -1e9, reverse=True)
        return reranked[:k]


# -----------------------------------------------------------------------------
# Demo / benchmark helpers
# -----------------------------------------------------------------------------

def build_system(bits: int = 8, dim: int = 256, clip_alpha: float = 0.25):
    store = MemoryStore()
    embedder = MockEmbeddingProvider(dim=dim)
    quantizer = ScalarQuantizer(bits=bits, clip_alpha=clip_alpha)
    indexer = MemoryIndexer(store, embedder, quantizer)
    retriever = MemoryRetriever(store, embedder, quantizer)
    return store, embedder, quantizer, indexer, retriever


def load_demo_memories(indexer: MemoryIndexer) -> None:
    memories = [
        ("m1", "TurboQuant paper proposes random rotation and scalar quantization for vector compression"),
        ("m2", "Agent memory MVP should use full precision embeddings and compressed shadow index"),
        ("m3", "KV cache quantization can reduce memory bandwidth for long context inference"),
        ("m4", "Blockchain agent should track wallets, transactions, and protocol risk"),
        ("m5", "Use exact reranking after approximate compressed retrieval to restore ranking quality"),
        ("m6", "Nearest neighbor retrieval benefits from preserving inner products and cosine similarity"),
        ("m7", "Research folder contains technical reports and condensed engineering notes"),
        ("m8", "4-bit quantization is more aggressive, 8-bit is safer for retrieval quality"),
    ]
    for memory_id, content in memories:
        indexer.ingest_memory(memory_id, content)


def print_results(title: str, results: List[SearchResult]) -> None:
    print(f"\n{title}")
    for i, r in enumerate(results, start=1):
        exact_str = f" exact={r.exact_score:.4f}" if r.exact_score is not None else ""
        print(f"{i:2d}. {r.memory_id} approx={r.approx_score:.4f}{exact_str} :: {r.content}")


def run_demo(bits: int) -> None:
    _, _, quantizer, indexer, retriever = build_system(bits=bits)
    load_demo_memories(indexer)

    print(f"Running demo with {quantizer.bits}-bit quantization, clip_alpha={quantizer.clip_alpha}")
    queries = [
        "compressed agent memory retrieval",
        "kv cache and quantization for long context",
        "blockchain transaction risk agent",
    ]

    for q in queries:
        print(f"\nQUERY: {q}")
        compressed = retriever.compressed_candidates(q, n_candidates=5)
        final = retriever.retrieve(q, k=3, n_candidates=5)
        exact = retriever.exact_search(q, k=3)
        print_results("Compressed-stage candidates:", compressed)
        print_results("Final reranked results:", final)
        print_results("Exact baseline:", exact)


def generate_synthetic_corpus(indexer: MemoryIndexer, n: int, seed: int = 7) -> List[str]:
    random.seed(seed)
    topics = [
        ("quant", ["quantization", "compression", "embedding", "vector", "retrieval"]),
        ("memory", ["agent", "memory", "context", "recall", "summary"]),
        ("llm", ["llm", "kv", "cache", "attention", "latency"]),
        ("blockchain", ["blockchain", "wallet", "transaction", "protocol", "risk"]),
        ("search", ["nearest", "neighbor", "ann", "cosine", "index"]),
    ]
    ids = []
    for i in range(n):
        label, words = random.choice(topics)
        noise = random.sample(words, k=min(3, len(words)))
        content = f"memory {i} about {label} with {' '.join(noise)} and note {random.randint(0, 999)}"
        memory_id = f"syn_{i}"
        indexer.ingest_memory(memory_id, content, memory_type=label)
        ids.append(memory_id)
    return ids


def recall_at_k(predicted: List[str], exact: List[str], k: int) -> float:
    return len(set(predicted[:k]) & set(exact[:k])) / max(1, len(set(exact[:k])))


def estimate_index_bytes(store: MemoryStore) -> Tuple[int, int]:
    float_bytes = 0
    compressed_bytes = 0
    for memory_id in store.memory_ids():
        emb = store.embeddings[memory_id]
        qrec = store.quantized[memory_id]
        float_bytes += len(emb.normalized_f32) * 4
        compressed_bytes += len(qrec.packed_codes)
    return float_bytes, compressed_bytes


def run_benchmark(bits: int, n_memories: int, n_queries: int, k: int, n_candidates: int) -> None:
    store, _, _, indexer, retriever = build_system(bits=bits)
    generate_synthetic_corpus(indexer, n_memories)

    query_topics = [
        "agent memory summary retrieval",
        "vector quantization and compression",
        "kv cache attention latency",
        "blockchain wallet transaction risk",
        "nearest neighbor cosine index",
    ]

    recalls_final = []
    recalls_candidates = []

    for i in range(n_queries):
        query = query_topics[i % len(query_topics)] + f" sample {i}"
        exact = retriever.exact_search(query, k=k)
        candidates = retriever.compressed_candidates(query, n_candidates=n_candidates)
        final = retriever.retrieve(query, k=k, n_candidates=n_candidates)

        exact_ids = [r.memory_id for r in exact]
        candidate_ids = [r.memory_id for r in candidates]
        final_ids = [r.memory_id for r in final]

        recalls_candidates.append(recall_at_k(candidate_ids, exact_ids, k))
        recalls_final.append(recall_at_k(final_ids, exact_ids, k))

    float_bytes, compressed_bytes = estimate_index_bytes(store)
    ratio = compressed_bytes / max(1, float_bytes)

    print("\nBenchmark results")
    print("-----------------")
    print(f"memories:               {n_memories}")
    print(f"queries:                {n_queries}")
    print(f"bits:                   {bits}")
    print(f"k:                      {k}")
    print(f"n_candidates:           {n_candidates}")
    print(f"avg candidate recall@k: {sum(recalls_candidates)/len(recalls_candidates):.4f}")
    print(f"avg final recall@k:     {sum(recalls_final)/len(recalls_final):.4f}")
    print(f"float index bytes:      {float_bytes}")
    print(f"compressed index bytes: {compressed_bytes}")
    print(f"compression ratio:      {ratio:.4f}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compressed agent memory MVP prototype")
    sub = parser.add_subparsers(dest="command", required=False)

    demo = sub.add_parser("demo", help="run small interactive demo")
    demo.add_argument("--bits", type=int, default=8, choices=[4, 8])

    bench = sub.add_parser("benchmark", help="run synthetic benchmark")
    bench.add_argument("--bits", type=int, default=8, choices=[4, 8])
    bench.add_argument("--memories", type=int, default=1000)
    bench.add_argument("--queries", type=int, default=50)
    bench.add_argument("--k", type=int, default=10)
    bench.add_argument("--candidates", type=int, default=50)

    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    cmd = args.command or "demo"

    if cmd == "demo":
        run_demo(bits=args.bits)
        return 0

    if cmd == "benchmark":
        run_benchmark(
            bits=args.bits,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
        )
        return 0

    print("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
