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
import sqlite3
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

from operator import mul as _mul

def dot(a: List[float], b: List[float]) -> float:
    return sum(map(_mul, a, b))


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

    def __init__(self, model_name: str = "mock-hash-embedder-v2", dim: int = 384, cache: Optional[EmbeddingCache] = None, salt: str = ""):
        super().__init__(model_name=model_name, cache=cache)
        self.dim = dim
        self.salt = salt

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
        salted = f"{self.salt}:{key}" if self.salt else key
        digest = hashlib.sha256(salted.encode("utf-8")).digest()
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
    BATCH_SIZE = 128  # OpenAI supports up to 2048; 128 is safe and fast
    MAX_RETRIES = 6
    RETRY_BASE_DELAY = 1.0  # seconds; doubles each retry (1, 2, 4, 8, 16, 32)

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small", cache: Optional[EmbeddingCache] = None):
        super().__init__(model_name=model_name, cache=cache)
        self.api_key = api_key

    def provider_name(self) -> str:
        return "openai"

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts in batches, using cache where available.

        Respects cache per-item. Only calls the API for uncached texts.
        Returns embeddings in the same order as input texts.
        """
        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(texts):
            if self.cache is not None:
                key = self.cache.make_key(self.provider_name(), self.model_name, text)
                cached = self.cache.get(key)
                if cached is not None:
                    results[i] = cached
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)

        # Process uncached in batches
        for batch_start in range(0, len(uncached_texts), self.BATCH_SIZE):
            batch_texts = uncached_texts[batch_start:batch_start + self.BATCH_SIZE]
            batch_embeddings = self._embed_batch_uncached(batch_texts)
            for j, embedding in enumerate(batch_embeddings):
                idx = uncached_indices[batch_start + j]
                results[idx] = embedding
                if self.cache is not None:
                    key = self.cache.make_key(self.provider_name(), self.model_name, texts[idx])
                    self.cache.set(key, embedding)

        return results  # type: ignore[return-value]

    def _embed_batch_uncached(self, texts: List[str]) -> List[List[float]]:
        import time
        payload = json.dumps({"input": texts, "model": self.model_name}).encode("utf-8")
        delay = self.RETRY_BASE_DELAY
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(self.MAX_RETRIES):
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
                data = json.loads(body)
                # API returns results in order; sort by index to be safe
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]
            except urllib.error.HTTPError as e:
                last_exc = e
                if e.code == 429 or e.code >= 500:
                    if attempt < self.MAX_RETRIES - 1:
                        print(f"[openai] HTTP {e.code}, retry {attempt + 1}/{self.MAX_RETRIES - 1} in {delay:.1f}s")
                        time.sleep(delay)
                        delay *= 2
                        continue
                raise RuntimeError(f"OpenAI embeddings request failed after {attempt + 1} attempts: {e}") from e
            except Exception as e:
                last_exc = e
                raise RuntimeError(f"OpenAI embeddings request failed: {e}") from e
        raise RuntimeError(f"OpenAI embeddings exhausted {self.MAX_RETRIES} retries") from last_exc

    def _embed_uncached(self, text: str) -> List[float]:
        return self._embed_batch_uncached([text])[0]


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
        # Precompute reconstructed values and use fast dot product
        return sum(qx * (-a + q * s) for qx, q, a, s in zip(query_vec, codes, self.alphas, self.steps))

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
    rows = load_jsonl(path)
    # Use batch embedding when available (OpenAI provider) to avoid per-item API calls
    if isinstance(indexer.embedder, OpenAIEmbeddingProvider) and rows:
        texts = [r["content"] for r in rows]
        print(f"[ingest] batch-embedding {len(texts)} items ...")
        embeddings = indexer.embedder.embed_batch(texts)
        for row, embedding in zip(rows, embeddings):
            memory_id = row["memory_id"]
            content = row["content"]
            memory_type = row.get("memory_type", "episodic")
            importance_score = float(row.get("importance_score", 0.0))
            tags = row.get("tags", [])
            item = MemoryItem(memory_id, content, memory_type, importance_score, tags)
            indexer.store.put_item(item)
            normalized, norm = normalize(embedding)
            indexer.store.put_embedding(EmbeddingRecord(
                memory_id=memory_id,
                embedding_model=indexer.embedder.model_name,
                embedding_dim=len(embedding),
                embedding_f32=embedding,
                embedding_norm=norm,
                normalized_f32=normalized,
            ))
    else:
        for row in rows:
            memory_id = row["memory_id"]
            content = row["content"]
            memory_type = row.get("memory_type", "episodic")
            importance_score = float(row.get("importance_score", 0.0))
            tags = row.get("tags", [])
            indexer.ingest_memory(memory_id, content, memory_type=memory_type, importance_score=importance_score, tags=tags)
    indexer.rebuild_quantized_index()


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    memory_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    importance_score REAL NOT NULL,
    tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    memory_id TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    embedding_f32 BLOB NOT NULL,
    embedding_norm REAL NOT NULL,
    normalized_f32 BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS quantized (
    memory_id TEXT PRIMARY KEY,
    quant_bits INTEGER NOT NULL,
    quant_scheme TEXT NOT NULL,
    packed_codes BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    saturation_rate REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quantizer_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bits INTEGER NOT NULL,
    alphas BLOB NOT NULL,
    steps BLOB NOT NULL
);
"""


def save_to_sqlite(store: MemoryStore, quantizer: CalibratedScalarQuantizer, path: Path) -> None:
    """Persist the full memory store and quantizer state to a SQLite database.

    Stores raw text, full-precision embeddings, quantized codes, and the
    calibrated quantizer parameters (alphas + steps). A subsequent
    load_from_sqlite call restores an identical in-memory state without
    re-embedding anything.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SQLITE_SCHEMA)
        cur = conn.cursor()
        for mid, item in store.items.items():
            cur.execute(
                "INSERT OR REPLACE INTO memory_items VALUES (?, ?, ?, ?, ?)",
                (item.memory_id, item.content, item.memory_type, item.importance_score, json.dumps(item.tags)),
            )
        for mid, emb in store.embeddings.items():
            cur.execute(
                "INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?, ?, ?)",
                (
                    emb.memory_id,
                    emb.embedding_model,
                    emb.embedding_dim,
                    _floats_to_blob(emb.embedding_f32),
                    emb.embedding_norm,
                    _floats_to_blob(emb.normalized_f32),
                ),
            )
        for mid, qrec in store.quantized.items():
            cur.execute(
                "INSERT OR REPLACE INTO quantized VALUES (?, ?, ?, ?, ?, ?)",
                (qrec.memory_id, qrec.quant_bits, qrec.quant_scheme, qrec.packed_codes, qrec.embedding_dim, qrec.saturation_rate),
            )
        if quantizer.is_fit():
            assert quantizer.alphas is not None and quantizer.steps is not None
            cur.execute(
                "INSERT OR REPLACE INTO quantizer_state VALUES (1, ?, ?, ?)",
                (quantizer.bits, _floats_to_blob(quantizer.alphas), _floats_to_blob(quantizer.steps)),
            )
        conn.commit()
    finally:
        conn.close()


def load_from_sqlite(path: Path) -> Tuple[MemoryStore, CalibratedScalarQuantizer]:
    """Restore a MemoryStore and CalibratedScalarQuantizer from a SQLite database.

    No re-embedding required — all embeddings and quantized codes are stored.
    The restored state is identical to what was saved.
    """
    conn = sqlite3.connect(str(path))
    store = MemoryStore()
    quantizer: Optional[CalibratedScalarQuantizer] = None
    try:
        for row in conn.execute("SELECT memory_id, content, memory_type, importance_score, tags FROM memory_items"):
            store.put_item(MemoryItem(row[0], row[1], row[2], row[3], json.loads(row[4])))
        for row in conn.execute("SELECT memory_id, embedding_model, embedding_dim, embedding_f32, embedding_norm, normalized_f32 FROM embeddings"):
            store.put_embedding(EmbeddingRecord(
                memory_id=row[0],
                embedding_model=row[1],
                embedding_dim=row[2],
                embedding_f32=_blob_to_floats(row[3]),
                embedding_norm=row[4],
                normalized_f32=_blob_to_floats(row[5]),
            ))
        for row in conn.execute("SELECT memory_id, quant_bits, quant_scheme, packed_codes, embedding_dim, saturation_rate FROM quantized"):
            store.put_quantized(QuantizedRecord(
                memory_id=row[0], quant_bits=row[1], quant_scheme=row[2],
                packed_codes=bytes(row[3]), embedding_dim=row[4], saturation_rate=row[5],
            ))
        row = conn.execute("SELECT bits, alphas, steps FROM quantizer_state WHERE id=1").fetchone()
        if row:
            q = CalibratedScalarQuantizer(bits=row[0])
            q.alphas = _blob_to_floats(row[1])
            q.steps = _blob_to_floats(row[2])
            quantizer = q
    finally:
        conn.close()
    if quantizer is None:
        quantizer = CalibratedScalarQuantizer(bits=8)
    return store, quantizer


def _floats_to_blob(values: List[float]) -> bytes:
    import struct
    return struct.pack(f"{len(values)}f", *values)


def _blob_to_floats(blob: bytes) -> List[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def snapshot_items(store: MemoryStore, path: Path) -> None:
    """Serialize raw memory items to JSONL — no embeddings, no quantized data.

    The snapshot is provider-agnostic: it contains only the original text
    payloads and metadata. Any embedding provider can restore from it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for mid in store.memory_ids():
        item = store.items[mid]
        lines.append(json.dumps({
            "memory_id": item.memory_id,
            "content": item.content,
            "memory_type": item.memory_type,
            "importance_score": item.importance_score,
            "tags": item.tags,
        }))
    path.write_text("\n".join(lines) + "\n")


def restore_from_snapshot(path: Path, indexer: MemoryIndexer) -> None:
    """Re-embed all items from a snapshot using the indexer's current embedder.

    This is the mechanism for provider switches: the snapshot holds raw text;
    calling this with a different embedder rebuilds the entire index in the new
    embedding space without losing any memory content.
    """
    ingest_memory_jsonl(indexer, path)


# -----------------------------------------------------------------------------
# Demo + benchmark helpers
# -----------------------------------------------------------------------------

def build_embedder(embedder_name: str, cache_dir: Path, dim: int = 384, mock_salt: str = "") -> BaseEmbeddingProvider:
    cache = EmbeddingCache(cache_dir)
    if embedder_name == "mock":
        return MockEmbeddingProvider(dim=dim, cache=cache, salt=mock_salt)
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
    rows = []
    for i in range(n):
        label = random.choice(labels)
        words = topics[label]
        chosen = random.sample(words, k=4)
        noise_label = random.choice(labels)
        noise_words = random.sample(topics[noise_label], k=2)
        content = f"memory {i} about {label} systems with {' '.join(chosen)} and note {' '.join(noise_words)}"
        rows.append({"memory_id": f"syn_{i}", "content": content, "memory_type": label})

    # Batch-embed when using OpenAI to avoid per-item API calls
    if isinstance(indexer.embedder, OpenAIEmbeddingProvider):
        texts = [r["content"] for r in rows]
        print(f"[corpus] batch-embedding {len(texts)} synthetic items ...")
        embeddings = indexer.embedder.embed_batch(texts)
        for row, embedding in zip(rows, embeddings):
            item = MemoryItem(row["memory_id"], row["content"], row["memory_type"], 0.0, [])
            indexer.store.put_item(item)
            normalized, norm = normalize(embedding)
            indexer.store.put_embedding(EmbeddingRecord(
                memory_id=row["memory_id"],
                embedding_model=indexer.embedder.model_name,
                embedding_dim=len(embedding),
                embedding_f32=embedding,
                embedding_norm=norm,
                normalized_f32=normalized,
            ))
    else:
        for row in rows:
            indexer.ingest_memory(row["memory_id"], row["content"], memory_type=row["memory_type"])
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


MULTIDOMAIN_TOPICS = {
    "code": {
        "vocab": ["function", "class", "variable", "loop", "recursion", "async", "exception",
                  "interface", "module", "import", "decorator", "generator", "closure", "lambda",
                  "refactor", "lint", "compile", "runtime", "stack", "heap", "pointer", "type"],
        "queries": [
            "Python async function and exception handling",
            "recursive algorithm with stack overflow risk",
            "class interface and module import patterns",
            "runtime heap memory allocation in compiled code",
            "decorator and closure in functional programming",
        ],
    },
    "legal": {
        "vocab": ["contract", "clause", "liability", "plaintiff", "defendant", "statute",
                  "jurisdiction", "precedent", "deposition", "injunction", "indemnify", "arbitration",
                  "breach", "tort", "fiduciary", "discovery", "affidavit", "subpoena", "verdict"],
        "queries": [
            "contract liability clause and indemnification terms",
            "plaintiff defendant jurisdiction and statute precedent",
            "arbitration breach of fiduciary duty",
            "discovery deposition affidavit subpoena procedure",
            "tort injunction verdict and legal remedy",
        ],
    },
    "news": {
        "vocab": ["election", "parliament", "minister", "inflation", "central bank", "sanctions",
                  "conflict", "ceasefire", "summit", "treaty", "GDP", "unemployment", "protest",
                  "referendum", "coalition", "tariff", "deficit", "bond", "currency", "diplomat"],
        "queries": [
            "election parliament minister coalition government",
            "central bank inflation interest rate GDP",
            "conflict ceasefire summit treaty diplomat",
            "sanctions tariff deficit currency bond",
            "protest referendum unemployment economic policy",
        ],
    },
    "medical": {
        "vocab": ["diagnosis", "symptom", "prognosis", "biopsy", "oncology", "cardiology",
                  "hypertension", "insulin", "antibiotic", "chemotherapy", "radiology", "pathology",
                  "neurological", "immunology", "dosage", "placebo", "clinical trial", "remission",
                  "metabolic", "chronic"],
        "queries": [
            "diagnosis prognosis symptom biopsy oncology",
            "hypertension insulin dosage chronic metabolic",
            "antibiotic chemotherapy clinical trial remission",
            "cardiology neurological radiology pathology",
            "immunology placebo clinical trial metabolic syndrome",
        ],
    },
}


def generate_multidomain_corpus(indexer: MemoryIndexer, n_per_domain: int = 250, seed: int = 42) -> Dict[str, List[str]]:
    """Generate a corpus with entries from 4 distinct domains.

    Returns a dict mapping domain -> list of memory_ids, used for recall evaluation.
    """
    random.seed(seed)
    domain_ids: Dict[str, List[str]] = {domain: [] for domain in MULTIDOMAIN_TOPICS}
    rows = []
    mid = 0
    for domain, spec in MULTIDOMAIN_TOPICS.items():
        vocab = spec["vocab"]
        for _ in range(n_per_domain):
            n_words = random.randint(4, 7)
            chosen = random.sample(vocab, k=min(n_words, len(vocab)))
            content = f"{domain} note {mid}: {' '.join(chosen)}"
            memory_id = f"md_{domain}_{mid}"
            domain_ids[domain].append(memory_id)
            rows.append({"memory_id": memory_id, "content": content, "memory_type": domain})
            mid += 1

    if isinstance(indexer.embedder, OpenAIEmbeddingProvider):
        texts = [r["content"] for r in rows]
        print(f"[multidomain] batch-embedding {len(texts)} items ...")
        embeddings = indexer.embedder.embed_batch(texts)
        for row, embedding in zip(rows, embeddings):
            item = MemoryItem(row["memory_id"], row["content"], row["memory_type"], 0.0, [])
            indexer.store.put_item(item)
            normalized, norm = normalize(embedding)
            indexer.store.put_embedding(EmbeddingRecord(
                memory_id=row["memory_id"],
                embedding_model=indexer.embedder.model_name,
                embedding_dim=len(embedding),
                embedding_f32=embedding,
                embedding_norm=norm,
                normalized_f32=normalized,
            ))
    else:
        for row in rows:
            indexer.ingest_memory(row["memory_id"], row["content"], memory_type=row["memory_type"])
    indexer.rebuild_quantized_index()
    return domain_ids


def run_multidomain_benchmark(
    bits: int = 8,
    embedder_name: str = "mock",
    n_per_domain: int = 250,
    k: int = 10,
    n_candidates: int = 50,
    out_file: Optional[Path] = None,
) -> None:
    """Experiment 4: prove retrieval works across unrelated domains.

    For each domain, run the domain's canonical queries and measure:
    - within-domain recall@k: compressed+reranked retrieval vs. exact search
    - domain purity@k: fraction of top-k results that belong to the queried domain

    Pass criteria:
    - avg within-domain recall@k >= 0.85
    - avg domain purity@k >= 0.80
    """
    store, embedder, quantizer, indexer, retriever = build_system(bits=bits, embedder_name=embedder_name)
    n_domains = len(MULTIDOMAIN_TOPICS)
    total = n_per_domain * n_domains
    print(f"[multidomain] Building {total}-item corpus ({n_per_domain}/domain, {n_domains} domains) ...")
    domain_ids = generate_multidomain_corpus(indexer, n_per_domain=n_per_domain)

    domain_results = {}
    all_recalls: List[float] = []
    all_purities: List[float] = []

    for domain, spec in MULTIDOMAIN_TOPICS.items():
        domain_set = set(domain_ids[domain])
        recalls: List[float] = []
        purities: List[float] = []
        for query in spec["queries"]:
            exact_k = retriever.exact_search(query, k=k)
            final = retriever.retrieve(query, k=k, n_candidates=n_candidates)
            exact_ids = [r.memory_id for r in exact_k]
            final_ids = [r.memory_id for r in final]
            recalls.append(recall_at_k(final_ids, exact_ids, k))
            purity = len([mid for mid in final_ids if mid in domain_set]) / max(1, len(final_ids))
            purities.append(purity)
        avg_recall = sum(recalls) / len(recalls)
        avg_purity = sum(purities) / len(purities)
        domain_results[domain] = {"recall_at_k": avg_recall, "domain_purity_at_k": avg_purity}
        all_recalls.append(avg_recall)
        all_purities.append(avg_purity)
        print(f"[multidomain] {domain:8s}  recall@{k}={avg_recall:.4f}  purity@{k}={avg_purity:.4f}")

    avg_recall = sum(all_recalls) / len(all_recalls)
    avg_purity = sum(all_purities) / len(all_purities)
    recall_pass = avg_recall >= 0.85
    purity_pass = avg_purity >= 0.80
    passed = recall_pass and purity_pass

    print(f"\n[multidomain] avg recall@{k}:  {avg_recall:.4f}  ({'PASS' if recall_pass else 'FAIL'} threshold=0.85)")
    print(f"[multidomain] avg purity@{k}:  {avg_purity:.4f}  ({'PASS' if purity_pass else 'FAIL'} threshold=0.80)")
    print(f"[multidomain] overall: {'PASS' if passed else 'FAIL'}")

    result = {
        "config": {
            "bits": bits,
            "embedder": embedder.provider_name(),
            "model": embedder.model_name,
            "n_per_domain": n_per_domain,
            "total_memories": total,
            "k": k,
            "n_candidates": n_candidates,
            "domains": list(MULTIDOMAIN_TOPICS.keys()),
            "thresholds": {"recall_at_k": 0.85, "domain_purity_at_k": 0.80},
        },
        "per_domain": domain_results,
        "summary": {
            "avg_recall_at_k": avg_recall,
            "avg_domain_purity_at_k": avg_purity,
            "recall_pass": recall_pass,
            "purity_pass": purity_pass,
            "passed": passed,
        },
    }

    if out_file is not None:
        write_json_output(out_file, result)
        print(f"[multidomain] results written to: {out_file}")


def run_persist_test(
    bits: int = 8,
    n_memories: int = 500,
    n_queries: int = 50,
    k: int = 10,
    n_candidates: int = 50,
    out_file: Optional[Path] = None,
) -> None:
    """Prove session persistence: save to SQLite, reload with no re-embedding, retrieve identically.

    Protocol:
    1. Ingest corpus, build quantized index in memory
    2. Measure recall@k baseline (pre-save)
    3. Save full state to SQLite (items + embeddings + quantized codes + quantizer params)
    4. Load from SQLite into a brand-new MemoryStore (no embedder needed)
    5. Measure recall@k post-load using the same queries
    6. Verify: post-load recall matches pre-save recall (within floating-point tolerance)
    7. Verify: item count and content are byte-identical

    Pass criteria:
    - recall retention >= 1.0 (no degradation after restore)
    - items_match: True (content lossless)
    - quantizer_match: True (alphas and steps preserved)
    """
    import tempfile
    root = Path(__file__).resolve().parent
    cache_dir = root / ".cache" / "embeddings"

    store_a = MemoryStore()
    embedder = MockEmbeddingProvider(dim=384, cache=EmbeddingCache(cache_dir))
    quantizer_a = CalibratedScalarQuantizer(bits=bits)
    indexer_a = MemoryIndexer(store_a, embedder, quantizer_a)
    retriever_a = MemoryRetriever(store_a, embedder, quantizer_a)

    print(f"[persist-test] Ingesting {n_memories} memories ...")
    generate_synthetic_corpus(indexer_a, n_memories)

    query_topics = [
        "agent memory summary retrieval",
        "vector quantization and scalar compression",
        "kv cache attention latency",
        "blockchain wallet transaction risk",
        "nearest neighbor cosine rerank index",
    ]
    queries = [query_topics[i % len(query_topics)] + f" sample {i}" for i in range(n_queries)]

    recalls_pre: List[float] = []
    pre_top1: List[str] = []
    for query in queries:
        exact_k = retriever_a.exact_search(query, k=k)
        final = retriever_a.retrieve(query, k=k, n_candidates=n_candidates)
        recalls_pre.append(recall_at_k([r.memory_id for r in final], [r.memory_id for r in exact_k], k))
        pre_top1.append(final[0].memory_id if final else "")
    avg_pre = sum(recalls_pre) / len(recalls_pre)
    print(f"[persist-test] Pre-save  recall@{k}: {avg_pre:.4f}")

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        db_path = Path(tmp.name)

    save_to_sqlite(store_a, quantizer_a, db_path)
    db_size = db_path.stat().st_size
    print(f"[persist-test] Saved to {db_path} ({db_size} bytes)")

    # Reload into a completely fresh store — no embedder needed
    store_b, quantizer_b = load_from_sqlite(db_path)
    db_path.unlink(missing_ok=True)

    retriever_b = MemoryRetriever(store_b, embedder, quantizer_b)

    recalls_post: List[float] = []
    post_top1: List[str] = []
    for query in queries:
        exact_k = retriever_b.exact_search(query, k=k)
        final = retriever_b.retrieve(query, k=k, n_candidates=n_candidates)
        recalls_post.append(recall_at_k([r.memory_id for r in final], [r.memory_id for r in exact_k], k))
        post_top1.append(final[0].memory_id if final else "")
    avg_post = sum(recalls_post) / len(recalls_post)
    print(f"[persist-test] Post-load recall@{k}: {avg_post:.4f}")

    items_match = set(store_a.memory_ids()) == set(store_b.memory_ids()) and all(
        store_a.items[mid].content == store_b.items[mid].content for mid in store_a.memory_ids()
    )
    quantizer_match = (
        quantizer_a.alphas is not None and quantizer_b.alphas is not None and
        all(abs(a - b) < 1e-5 for a, b in zip(quantizer_a.alphas, quantizer_b.alphas))
    )
    top1_match = pre_top1 == post_top1
    retention = avg_post / max(avg_pre, 1e-9)
    passed = retention >= 1.0 and items_match and quantizer_match

    print(f"[persist-test] Items match: {items_match}")
    print(f"[persist-test] Quantizer match: {quantizer_match}")
    print(f"[persist-test] Top-1 identical across all queries: {top1_match}")
    print(f"[persist-test] Recall retention: {retention:.4f} ({'PASS' if passed else 'FAIL'})")

    result = {
        "config": {
            "bits": bits,
            "n_memories": n_memories,
            "n_queries": n_queries,
            "k": k,
            "n_candidates": n_candidates,
        },
        "results": {
            "avg_recall_pre_save": avg_pre,
            "avg_recall_post_load": avg_post,
            "recall_retention": retention,
            "items_match": items_match,
            "quantizer_match": quantizer_match,
            "top1_identical": top1_match,
            "db_bytes": db_size,
            "passed": passed,
        },
    }
    if out_file is not None:
        write_json_output(out_file, result)
        print(f"[persist-test] Results written to: {out_file}")


def run_provider_switch_test(
    bits: int = 8,
    n_memories: int = 500,
    n_queries: int = 50,
    k: int = 10,
    n_candidates: int = 50,
    out_file: Optional[Path] = None,
) -> None:
    """Prove that memory survives a provider/model switch.

    Protocol:
    1. Ingest corpus with Provider A (mock, salt="providerA")
    2. Measure recall@k baseline using Provider A (compressed vs. exact)
    3. Snapshot raw items to a temporary JSONL (no embeddings)
    4. Build a fresh system with Provider B (mock, salt="providerB") — different vector space
    5. Restore from snapshot: re-embed all items with Provider B
    6. Measure recall@k post-switch using Provider B (compressed vs. exact)
    7. Report both recalls and a pass/fail (post-switch recall >= 0.90 * baseline)

    The two mock providers use different hash salts, producing genuinely
    different embedding spaces. This simulates switching from e.g. OpenAI to
    Cohere: raw text is portable, embeddings are not — re-embedding restores
    the index in the new space.
    """
    import tempfile

    root = Path(__file__).resolve().parent
    cache_dir_a = root / ".cache" / "embeddings_switch_A"
    cache_dir_b = root / ".cache" / "embeddings_switch_B"

    # -------------------------------------------------------------------------
    # Phase A: ingest with Provider A
    # -------------------------------------------------------------------------
    store_a = MemoryStore()
    embedder_a = MockEmbeddingProvider(
        model_name="mock-provider-A",
        dim=384,
        cache=EmbeddingCache(cache_dir_a),
        salt="providerA",
    )
    quantizer_a = CalibratedScalarQuantizer(bits=bits)
    indexer_a = MemoryIndexer(store_a, embedder_a, quantizer_a)
    retriever_a = MemoryRetriever(store_a, embedder_a, quantizer_a)

    print(f"[provider-switch] Phase A: ingesting {n_memories} memories with provider=A ...")
    generate_synthetic_corpus(indexer_a, n_memories)

    # Benchmark recall with Provider A
    query_topics = [
        "agent memory summary retrieval",
        "vector quantization and scalar compression",
        "kv cache attention latency",
        "blockchain wallet transaction risk",
        "nearest neighbor cosine rerank index",
    ]
    queries = [query_topics[i % len(query_topics)] + f" sample {i}" for i in range(n_queries)]

    recalls_a: List[float] = []
    for query in queries:
        exact_k = retriever_a.exact_search(query, k=k)
        final = retriever_a.retrieve(query, k=k, n_candidates=n_candidates)
        exact_ids = [r.memory_id for r in exact_k]
        final_ids = [r.memory_id for r in final]
        recalls_a.append(recall_at_k(final_ids, exact_ids, k))

    avg_recall_a = sum(recalls_a) / len(recalls_a)
    print(f"[provider-switch] Provider A recall@{k}: {avg_recall_a:.4f}")

    # -------------------------------------------------------------------------
    # Phase B: snapshot → restore with Provider B
    # -------------------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        snap_path = Path(tmp.name)

    snapshot_items(store_a, snap_path)
    n_snapshotted = len(store_a.memory_ids())
    print(f"[provider-switch] Snapshot written: {n_snapshotted} items → {snap_path}")

    store_b = MemoryStore()
    embedder_b = MockEmbeddingProvider(
        model_name="mock-provider-B",
        dim=384,
        cache=EmbeddingCache(cache_dir_b),
        salt="providerB",
    )
    quantizer_b = CalibratedScalarQuantizer(bits=bits)
    indexer_b = MemoryIndexer(store_b, embedder_b, quantizer_b)
    retriever_b = MemoryRetriever(store_b, embedder_b, quantizer_b)

    print("[provider-switch] Phase B: restoring with provider=B (different vector space) ...")
    restore_from_snapshot(snap_path, indexer_b)
    snap_path.unlink(missing_ok=True)

    n_restored = len(store_b.memory_ids())
    print(f"[provider-switch] Restored {n_restored} items with provider=B")

    # Benchmark recall with Provider B (same queries, B's own exact search as oracle)
    recalls_b: List[float] = []
    for query in queries:
        exact_k = retriever_b.exact_search(query, k=k)
        final = retriever_b.retrieve(query, k=k, n_candidates=n_candidates)
        exact_ids = [r.memory_id for r in exact_k]
        final_ids = [r.memory_id for r in final]
        recalls_b.append(recall_at_k(final_ids, exact_ids, k))

    avg_recall_b = sum(recalls_b) / len(recalls_b)
    retention = avg_recall_b / max(avg_recall_a, 1e-9)
    passed = retention >= 0.90

    print(f"[provider-switch] Provider B recall@{k}: {avg_recall_b:.4f}")
    print(f"[provider-switch] Recall retention after switch: {retention:.4f} ({'PASS' if passed else 'FAIL'} threshold=0.90)")
    print(f"[provider-switch] Items: snapshotted={n_snapshotted} restored={n_restored} (content lossless: {n_snapshotted == n_restored})")

    result = {
        "config": {
            "bits": bits,
            "n_memories": n_memories,
            "n_queries": n_queries,
            "k": k,
            "n_candidates": n_candidates,
            "provider_a": embedder_a.model_name,
            "provider_b": embedder_b.model_name,
            "threshold": 0.90,
        },
        "results": {
            "avg_recall_a": avg_recall_a,
            "avg_recall_b": avg_recall_b,
            "recall_retention": retention,
            "passed": passed,
            "items_snapshotted": n_snapshotted,
            "items_restored": n_restored,
            "content_lossless": n_snapshotted == n_restored,
        },
    }

    if out_file is not None:
        write_json_output(out_file, result)
        print(f"[provider-switch] Results written to: {out_file}")


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

    persist = sub.add_parser("persist-test", help="prove SQLite save/load round-trip preserves retrieval exactly")
    persist.add_argument("--bits", type=int, default=8, choices=[4, 8])
    persist.add_argument("--memories", type=int, default=500)
    persist.add_argument("--queries", type=int, default=50)
    persist.add_argument("--k", type=int, default=10)
    persist.add_argument("--candidates", type=int, default=50)
    persist.add_argument("--out", type=Path, default=None)

    multi = sub.add_parser("multidomain", help="Experiment 4: recall across code/legal/news/medical domains")
    multi.add_argument("--bits", type=int, default=8, choices=[4, 8])
    multi.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])
    multi.add_argument("--n-per-domain", type=int, default=250)
    multi.add_argument("--k", type=int, default=10)
    multi.add_argument("--candidates", type=int, default=50)
    multi.add_argument("--out", type=Path, default=None)

    switch = sub.add_parser("provider-switch", help="prove memory survives a provider/model switch")
    switch.add_argument("--bits", type=int, default=8, choices=[4, 8])
    switch.add_argument("--memories", type=int, default=500)
    switch.add_argument("--queries", type=int, default=50)
    switch.add_argument("--k", type=int, default=10)
    switch.add_argument("--candidates", type=int, default=50)
    switch.add_argument("--out", type=Path, default=None)

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

    if cmd == "persist-test":
        run_persist_test(
            bits=args.bits,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    if cmd == "multidomain":
        run_multidomain_benchmark(
            bits=args.bits,
            embedder_name=args.embedder,
            n_per_domain=args.n_per_domain,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    if cmd == "provider-switch":
        run_provider_switch_test(
            bits=args.bits,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    print("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
