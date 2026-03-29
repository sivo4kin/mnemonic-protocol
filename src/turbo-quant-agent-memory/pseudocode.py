"""
Runnable compressed agent memory MVP prototype.

Features:
- full-precision normalized vectors kept for exact rerank
- compressed shadow index used for candidate generation
- corpus-calibrated per-dimension quantization
- supports both offline mock embeddings and real OpenAI embeddings
- simple local embedding cache on disk
- supports benchmarking from real JSONL datasets
- supports JSON result export

Still intentionally compact:
- standard library only
- no random rotation / QJL
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import argparse
import hashlib
import heapq
import json
import math
import os
import random
import statistics
import sys
import urllib.request


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
# Embedding cache
# -----------------------------------------------------------------------------

class EmbeddingCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def make_key(self, provider: str, model: str, text: str) -> str:
        return hashlib.sha256(f"{provider}\n{model}\n{text}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[List[float]]:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        return json.loads(path.read_text())["embedding"]

    def set(self, key: str, embedding: List[float]) -> None:
        path = self._path_for_key(key)
        path.write_text(json.dumps({"embedding": embedding}))


# -----------------------------------------------------------------------------
# Embedding providers
# -----------------------------------------------------------------------------

class BaseEmbeddingProvider:
    def __init__(self, model_name: str, cache: Optional[EmbeddingCache] = None):
        self.model_name = model_name
        self.cache = cache

    def provider_name(self) -> str:
        raise NotImplementedError

    def embed_text(self, text: str) -> List[float]:
        if self.cache is None:
            return self._embed_uncached(text)
        key = self.cache.make_key(self.provider_name(), self.model_name, text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        embedding = self._embed_uncached(text)
        self.cache.set(key, embedding)
        return embedding

    def _embed_uncached(self, text: str) -> List[float]:
        raise NotImplementedError


class MockEmbeddingProvider(BaseEmbeddingProvider):
    DOMAIN_KEYWORDS = {
        "quantization": ["quantization", "quant", "compression", "compressed", "scalar"],
        "memory": ["memory", "recall", "context", "episodic", "semantic"],
        "retrieval": ["retrieval", "search", "rerank", "candidate", "nearest"],
        "llm": ["llm", "kv", "cache", "attention", "inference"],
        "blockchain": ["blockchain", "wallet", "transaction", "protocol", "risk"],
        "agent": ["agent", "tool", "planner", "autonomy", "task"],
    }

    def __init__(self, model_name: str = "mock-hash-embedder-v2", dim: int = 384, cache: Optional[EmbeddingCache] = None):
        super().__init__(model_name=model_name, cache=cache)
        self.dim = dim

    def provider_name(self) -> str:
        return "mock"

    def _embed_uncached(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        lowered = text.lower()
        tokens = self._tokenize(lowered)
        if not tokens:
            return vec

        for token in tokens:
            self._signed_hash_add(vec, f"w:{token}", 1.0)
            if len(token) > 4:
                self._signed_hash_add(vec, f"stem:{token[:5]}", 0.35)

        for i in range(len(tokens) - 1):
            self._signed_hash_add(vec, f"b:{tokens[i]}_{tokens[i + 1]}", 0.65)

        for group_idx, (group, words) in enumerate(self.DOMAIN_KEYWORDS.items()):
            count = sum(lowered.count(word) for word in words)
            if count:
                vec[group_idx] += 1.25 * count
                self._signed_hash_add(vec, f"domain:{group}", 0.9 * count)

        vec[20] += len(tokens) / 30.0
        vec[21] += len(set(tokens)) / max(1, len(tokens))
        vec[22] += sum(ch.isdigit() for ch in lowered) / 10.0
        vec[23] += lowered.count("-") / 5.0
        return vec

    def _signed_hash_add(self, vec: List[float], key: str, weight: float) -> None:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        idx1 = int.from_bytes(digest[0:4], "big") % self.dim
        idx2 = int.from_bytes(digest[4:8], "big") % self.dim
        idx3 = int.from_bytes(digest[8:12], "big") % self.dim
        sign1 = 1.0 if digest[12] % 2 == 0 else -1.0
        sign2 = 1.0 if digest[13] % 2 == 0 else -1.0
        sign3 = 1.0 if digest[14] % 2 == 0 else -1.0
        vec[idx1] += sign1 * weight
        vec[idx2] += sign2 * weight * 0.5
        vec[idx3] += sign3 * weight * 0.25

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        out = []
        cur = []
        for ch in text:
            if ch.isalnum() or ch in {"-", "_"}:
                cur.append(ch)
            else:
                if cur:
                    out.append("".join(cur))
                    cur = []
        if cur:
            out.append("".join(cur))
        return out


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small", cache: Optional[EmbeddingCache] = None):
        super().__init__(model_name=model_name, cache=cache)
        self.api_key = api_key

    def provider_name(self) -> str:
        return "openai"

    def _embed_uncached(self, text: str) -> List[float]:
        payload = json.dumps({"input": text, "model": self.model_name}).encode("utf-8")
        req = urllib.request.Request(
            url="https://api.openai.com/v1/embeddings",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"OpenAI embeddings request failed: {e}") from e
        try:
            data = json.loads(body)
            return data["data"][0]["embedding"]
        except Exception as e:
            raise RuntimeError(f"Failed to parse OpenAI embeddings response: {e}; body={body[:500]}") from e


# -----------------------------------------------------------------------------
# Corpus-calibrated quantizer
# -----------------------------------------------------------------------------

class CalibratedScalarQuantizer:
    def __init__(self, bits: int = 8, default_alpha: float = 0.25):
        if bits not in (4, 8):
            raise ValueError("Only 4-bit and 8-bit modes are supported")
        self.bits = bits
        self.levels = 2 ** bits
        self.max_int = self.levels - 1
        self.default_alpha = default_alpha
        self.alphas: Optional[List[float]] = None
        self.steps: Optional[List[float]] = None

    def fit(self, vectors: List[List[float]]) -> None:
        if not vectors:
            raise ValueError("Need at least one vector to calibrate quantizer")
        dim = len(vectors[0])
        alphas = []
        steps = []
        for j in range(dim):
            values = [abs(v[j]) for v in vectors]
            ordered = sorted(values)
            idx = min(len(ordered) - 1, max(0, int(0.98 * (len(ordered) - 1))))
            alpha = max(ordered[idx], self.default_alpha / 8.0)
            alpha = min(alpha, 1.0)
            alphas.append(alpha)
            steps.append((2.0 * alpha) / self.max_int)
        self.alphas = alphas
        self.steps = steps

    def is_fit(self) -> bool:
        return self.alphas is not None and self.steps is not None

    def quantize_vector(self, vec: List[float]) -> Tuple[bytes, float]:
        if not self.is_fit():
            raise RuntimeError("Quantizer must be fit before use")
        codes: List[int] = []
        saturated = 0
        assert self.alphas is not None and self.steps is not None
        for x, alpha, step in zip(vec, self.alphas, self.steps):
            x_clipped = clip(x, -alpha, alpha)
            if x_clipped != x:
                saturated += 1
            q = round((x_clipped + alpha) / step)
            q = max(0, min(self.max_int, int(q)))
            codes.append(q)
        return self.pack_codes(codes), saturated / max(1, len(vec))

    def score_query_against_codes(self, query_vec: List[float], packed_codes: bytes, dim: int) -> float:
        if not self.is_fit():
            raise RuntimeError("Quantizer must be fit before use")
        assert self.alphas is not None and self.steps is not None
        codes = self.unpack_codes(packed_codes, dim)
        score = 0.0
        for qx, q, alpha, step in zip(query_vec, codes, self.alphas, self.steps):
            score += qx * (-alpha + q * step)
        return score

    def average_alpha(self) -> float:
        if not self.alphas:
            return self.default_alpha
        return sum(self.alphas) / len(self.alphas)

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


# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------

class MemoryRetriever:
    def __init__(self, store: MemoryStore, embedder: BaseEmbeddingProvider, quantizer: CalibratedScalarQuantizer):
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


# -----------------------------------------------------------------------------
# Dataset IO
# -----------------------------------------------------------------------------

def load_jsonl(path: Path) -> List[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def ingest_memory_jsonl(indexer: MemoryIndexer, path: Path) -> None:
    for row in load_jsonl(path):
        memory_id = row["memory_id"]
        content = row["content"]
        memory_type = row.get("memory_type", "episodic")
        importance_score = float(row.get("importance_score", 0.0))
        tags = row.get("tags", [])
        indexer.ingest_memory(memory_id, content, memory_type=memory_type, importance_score=importance_score, tags=tags)
    indexer.rebuild_quantized_index()


# -----------------------------------------------------------------------------
# Demo + benchmark helpers
# -----------------------------------------------------------------------------

def build_embedder(embedder_name: str, cache_dir: Path, dim: int = 384) -> BaseEmbeddingProvider:
    cache = EmbeddingCache(cache_dir)
    if embedder_name == "mock":
        return MockEmbeddingProvider(dim=dim, cache=cache)
    if embedder_name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when --embedder openai is selected")
        model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddingProvider(api_key=api_key, model_name=model, cache=cache)
    raise ValueError(f"Unknown embedder: {embedder_name}")


def build_system(bits: int = 8, embedder_name: str = "mock", dim: int = 384):
    root = Path(__file__).resolve().parent
    cache_dir = root / ".cache" / "embeddings"
    store = MemoryStore()
    embedder = build_embedder(embedder_name, cache_dir=cache_dir, dim=dim)
    quantizer = CalibratedScalarQuantizer(bits=bits)
    indexer = MemoryIndexer(store, embedder, quantizer)
    retriever = MemoryRetriever(store, embedder, quantizer)
    return store, embedder, quantizer, indexer, retriever


def load_demo_memories(indexer: MemoryIndexer) -> None:
    memories = [
        ("m1", "TurboQuant uses random rotation and scalar quantization for vector compression"),
        ("m2", "Agent memory MVP keeps full precision embeddings and a compressed shadow index"),
        ("m3", "KV cache quantization helps long context inference by reducing memory bandwidth"),
        ("m4", "Blockchain agent should track wallets, transactions, protocol risk, and alerts"),
        ("m5", "Exact reranking after compressed candidate retrieval restores final ranking quality"),
        ("m6", "Nearest neighbor retrieval depends on cosine similarity and inner product preservation"),
        ("m7", "Research notes discuss quantization, retrieval systems, and engineering tradeoffs"),
        ("m8", "4-bit quantization is aggressive while 8-bit quantization is safer for recall"),
        ("m9", "Agent memory architecture can use compressed indexing with exact rerank on top candidates"),
        ("m10", "Vector search systems benefit from candidate generation followed by precise reranking"),
    ]
    for memory_id, content in memories:
        indexer.ingest_memory(memory_id, content)
    indexer.rebuild_quantized_index()


def print_results(title: str, results: List[SearchResult]) -> None:
    print(f"\n{title}")
    for i, r in enumerate(results, start=1):
        exact = f" exact={r.exact_score:.4f}" if r.exact_score is not None else ""
        print(f"{i:2d}. {r.memory_id} approx={r.approx_score:.4f}{exact} :: {r.content}")


def run_demo(bits: int, embedder_name: str) -> None:
    _, embedder, quantizer, indexer, retriever = build_system(bits=bits, embedder_name=embedder_name)
    load_demo_memories(indexer)
    print(f"Running demo with embedder={embedder.provider_name()} model={embedder.model_name} bits={quantizer.bits} avg_alpha={quantizer.average_alpha():.4f}")
    queries = [
        "compressed agent memory retrieval",
        "kv cache quantization for long context",
        "blockchain wallet transaction risk agent",
    ]
    for q in queries:
        print(f"\nQUERY: {q}")
        compressed = retriever.compressed_candidates(q, n_candidates=5)
        final = retriever.retrieve(q, k=3, n_candidates=5)
        exact = retriever.exact_search(q, k=3)
        print_results("Compressed-stage candidates:", compressed)
        print_results("Final reranked results:", final)
        print_results("Exact baseline:", exact)


def generate_synthetic_corpus(indexer: MemoryIndexer, n: int, seed: int = 7) -> None:
    random.seed(seed)
    topics = {
        "quant": ["quantization", "compression", "vector", "embedding", "scalar", "clip", "calibration"],
        "memory": ["agent", "memory", "context", "recall", "summary", "episodic", "semantic"],
        "llm": ["llm", "kv", "cache", "attention", "latency", "inference", "context"],
        "blockchain": ["blockchain", "wallet", "transaction", "protocol", "risk", "bridge", "alert"],
        "search": ["nearest", "neighbor", "rerank", "candidate", "cosine", "index", "retrieval"],
    }
    labels = list(topics.keys())
    for i in range(n):
        label = random.choice(labels)
        words = topics[label]
        chosen = random.sample(words, k=4)
        noise_label = random.choice(labels)
        noise_words = random.sample(topics[noise_label], k=2)
        content = f"memory {i} about {label} systems with {' '.join(chosen)} and note {' '.join(noise_words)}"
        indexer.ingest_memory(f"syn_{i}", content, memory_type=label)
    indexer.rebuild_quantized_index()


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


def quant_diagnostics(store: MemoryStore) -> Tuple[float, float, float]:
    sats = [store.quantized[mid].saturation_rate for mid in store.memory_ids()]
    if not sats:
        return 0.0, 0.0, 0.0
    return min(sats), statistics.mean(sats), max(sats)


def evaluate_query_with_labels(retriever: MemoryRetriever, query: str, relevant_ids: List[str], k: int, n_candidates: int) -> Tuple[float, float, float]:
    candidates = retriever.compressed_candidates(query, n_candidates=n_candidates)
    final = retriever.retrieve(query, k=k, n_candidates=n_candidates)
    candidate_ids = [r.memory_id for r in candidates]
    final_ids = [r.memory_id for r in final]
    candidate_recall_k = recall_at_k(candidate_ids, relevant_ids, k)
    final_recall_k = recall_at_k(final_ids, relevant_ids, k)
    candidate_recall_c = recall_at_k(candidate_ids, relevant_ids, min(n_candidates, len(relevant_ids) or n_candidates))
    return candidate_recall_k, final_recall_k, candidate_recall_c


def write_json_output(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def run_benchmark(
    bits: int,
    embedder_name: str,
    n_memories: int,
    n_queries: int,
    k: int,
    n_candidates: int,
    memory_file: Optional[Path] = None,
    query_file: Optional[Path] = None,
    out_file: Optional[Path] = None,
) -> None:
    store, embedder, quantizer, indexer, retriever = build_system(bits=bits, embedder_name=embedder_name)

    query_rows: List[dict]
    dataset_mode: str

    if memory_file is not None:
        ingest_memory_jsonl(indexer, memory_file)
        dataset_mode = "jsonl"
    else:
        generate_synthetic_corpus(indexer, n_memories)
        dataset_mode = "synthetic"

    if query_file is not None:
        query_rows = load_jsonl(query_file)
    else:
        query_topics = [
            "agent memory summary retrieval",
            "vector quantization and scalar compression",
            "kv cache attention latency",
            "blockchain wallet transaction risk",
            "nearest neighbor cosine rerank index",
        ]
        query_rows = [{"query": query_topics[i % len(query_topics)] + f" sample {i}"} for i in range(n_queries)]

    candidate_recalls_at_k = []
    final_recalls_at_k = []
    candidate_recalls_at_candidates = []
    judged_mode = False

    for row in query_rows[:n_queries]:
        query = row["query"]
        relevant_ids = row.get("relevant_ids")

        if relevant_ids:
            judged_mode = True
            c_k, f_k, c_c = evaluate_query_with_labels(retriever, query, relevant_ids, k, n_candidates)
            candidate_recalls_at_k.append(c_k)
            final_recalls_at_k.append(f_k)
            candidate_recalls_at_candidates.append(c_c)
        else:
            exact_k = retriever.exact_search(query, k=k)
            exact_c = retriever.exact_search(query, k=n_candidates)
            candidates = retriever.compressed_candidates(query, n_candidates=n_candidates)
            final = retriever.retrieve(query, k=k, n_candidates=n_candidates)
            exact_ids_k = [r.memory_id for r in exact_k]
            exact_ids_c = [r.memory_id for r in exact_c]
            candidate_ids = [r.memory_id for r in candidates]
            final_ids = [r.memory_id for r in final]
            candidate_recalls_at_k.append(recall_at_k(candidate_ids, exact_ids_k, k))
            final_recalls_at_k.append(recall_at_k(final_ids, exact_ids_k, k))
            candidate_recalls_at_candidates.append(recall_at_k(candidate_ids, exact_ids_c, n_candidates))

    float_bytes, compressed_bytes = estimate_index_bytes(store)
    ratio = compressed_bytes / max(1, float_bytes)
    sat_min, sat_mean, sat_max = quant_diagnostics(store)

    metrics = {
        "avg_candidate_recall_at_k": sum(candidate_recalls_at_k) / len(candidate_recalls_at_k),
        "avg_final_recall_at_k": sum(final_recalls_at_k) / len(final_recalls_at_k),
        "avg_candidate_recall_at_candidates": sum(candidate_recalls_at_candidates) / len(candidate_recalls_at_candidates),
        "float_index_bytes": float_bytes,
        "compressed_index_bytes": compressed_bytes,
        "compression_ratio": ratio,
        "quant_avg_alpha": quantizer.average_alpha(),
        "saturation_rate_min": sat_min,
        "saturation_rate_mean": sat_mean,
        "saturation_rate_max": sat_max,
    }

    result = {
        "config": {
            "embedder": embedder.provider_name(),
            "model": embedder.model_name,
            "bits": bits,
            "k": k,
            "n_candidates": n_candidates,
            "dataset_mode": dataset_mode,
            "judged_mode": judged_mode,
            "memory_file": str(memory_file) if memory_file else None,
            "query_file": str(query_file) if query_file else None,
            "num_memories": len(store.memory_ids()),
            "num_queries": min(len(query_rows), n_queries),
        },
        "metrics": metrics,
    }

    print("\nBenchmark results")
    print("-----------------")
    print(f"embedder:                     {result['config']['embedder']} ({result['config']['model']})")
    print(f"dataset mode:                 {dataset_mode}")
    print(f"judged mode:                  {judged_mode}")
    print(f"memories:                     {result['config']['num_memories']}")
    print(f"queries:                      {result['config']['num_queries']}")
    print(f"bits:                         {bits}")
    print(f"k:                            {k}")
    print(f"n_candidates:                 {n_candidates}")
    print(f"avg candidate recall@k:       {metrics['avg_candidate_recall_at_k']:.4f}")
    print(f"avg final recall@k:           {metrics['avg_final_recall_at_k']:.4f}")
    print(f"avg candidate recall@cand:    {metrics['avg_candidate_recall_at_candidates']:.4f}")
    print(f"float index bytes:            {float_bytes}")
    print(f"compressed index bytes:       {compressed_bytes}")
    print(f"compression ratio:            {ratio:.4f}")
    print(f"quant avg alpha:              {metrics['quant_avg_alpha']:.4f}")
    print(f"saturation rate min/mean/max: {sat_min:.4f} / {sat_mean:.4f} / {sat_max:.4f}")

    if out_file is not None:
        write_json_output(out_file, result)
        print(f"results written to:           {out_file}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compressed agent memory MVP prototype")
    sub = parser.add_subparsers(dest="command", required=False)

    demo = sub.add_parser("demo", help="run small interactive demo")
    demo.add_argument("--bits", type=int, default=8, choices=[4, 8])
    demo.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])

    bench = sub.add_parser("benchmark", help="run benchmark")
    bench.add_argument("--bits", type=int, default=8, choices=[4, 8])
    bench.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])
    bench.add_argument("--memories", type=int, default=1000)
    bench.add_argument("--queries", type=int, default=50)
    bench.add_argument("--k", type=int, default=10)
    bench.add_argument("--candidates", type=int, default=50)
    bench.add_argument("--memory-file", type=Path, default=None)
    bench.add_argument("--query-file", type=Path, default=None)
    bench.add_argument("--out", type=Path, default=None)

    return parser.parse_args(argv)



def main(argv: List[str]) -> int:
    args = parse_args(argv)
    cmd = args.command or "demo"

    if cmd == "demo":
        run_demo(bits=args.bits, embedder_name=args.embedder)
        return 0

    if cmd == "benchmark":
        run_benchmark(
            bits=args.bits,
            embedder_name=args.embedder,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            memory_file=args.memory_file,
            query_file=args.query_file,
            out_file=args.out,
        )
        return 0

    print("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
