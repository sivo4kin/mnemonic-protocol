from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import List, Optional

from .cache import EmbeddingCache


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


class NomicEmbeddingProvider(BaseEmbeddingProvider):
    """Open-weights embedder via sentence-transformers (nomic-embed-text-v1.5, 768-dim)."""

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", cache: Optional[EmbeddingCache] = None):
        super().__init__(model_name=model_name, cache=cache)
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is required for --embedder nomic. "
                "Install with: pip install sentence-transformers"
            )
        self._model = SentenceTransformer(model_name, trust_remote_code=True)

    def provider_name(self) -> str:
        return "nomic"

    def _embed_uncached(self, text: str) -> List[float]:
        # nomic-embed-text-v1.5 expects a task prefix for queries/documents
        embedding = self._model.encode(f"search_document: {text}", normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding with per-item caching."""
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

        if uncached_texts:
            # nomic expects task prefix
            prefixed = [f"search_document: {t}" for t in uncached_texts]
            embeddings = self._model.encode(prefixed, normalize_embeddings=True, batch_size=32)
            for j, embedding in enumerate(embeddings):
                idx = uncached_indices[j]
                emb_list = embedding.tolist()
                results[idx] = emb_list
                if self.cache is not None:
                    key = self.cache.make_key(self.provider_name(), self.model_name, texts[idx])
                    self.cache.set(key, emb_list)

        return results  # type: ignore[return-value]

    def embed_query(self, text: str) -> List[float]:
        """Embed a query (uses search_query prefix instead of search_document)."""
        if self.cache is not None:
            key = self.cache.make_key(self.provider_name(), self.model_name, f"query:{text}")
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        embedding = self._model.encode(f"search_query: {text}", normalize_embeddings=True)
        result = embedding.tolist()
        if self.cache is not None:
            key = self.cache.make_key(self.provider_name(), self.model_name, f"query:{text}")
            self.cache.set(key, result)
        return result


def _has_embed_batch(embedder: BaseEmbeddingProvider) -> bool:
    """Check if an embedder supports efficient batch embedding."""
    return isinstance(embedder, (OpenAIEmbeddingProvider, NomicEmbeddingProvider))


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
    if embedder_name == "nomic":
        return NomicEmbeddingProvider(cache=cache)
    raise ValueError(f"Unknown embedder: {embedder_name}")
