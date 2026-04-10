"""
Latency benchmarking for compressed agent memory retrieval pipeline.

Instruments each stage of the retrieval pipeline with detailed timing,
and optionally uses numpy for acceleration. Compares pure-Python vs numpy
performance across multiple corpus sizes and quantization modes.

Usage:
    python bench_latency.py [--sizes 100,1000,5000] [--bits 8] [--queries 20] [--numpy] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mnemonic import (
    BaseEmbeddingProvider,
    CalibratedScalarQuantizer,
    MemoryIndexer,
    MemoryRetriever,
    MemoryStore,
    MockEmbeddingProvider,
    build_system,
    clip,
    dot,
    generate_synthetic_corpus,
    normalize,
)

# ---------------------------------------------------------------------------
# Numpy acceleration layer (optional)
# ---------------------------------------------------------------------------

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False


def numpy_dot(a: List[float], b: List[float]) -> float:
    """Vectorized dot product using numpy."""
    return float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def numpy_batch_score(query: List[float], matrix: "np.ndarray") -> "np.ndarray":
    """Score query against all row-vectors at once via matrix multiply.

    Args:
        query: 1-D list of floats (dim,)
        matrix: 2-D ndarray of shape (n, dim)

    Returns:
        1-D ndarray of shape (n,) with similarity scores.
    """
    q = np.asarray(query, dtype=np.float32)
    return matrix @ q


def numpy_quantize(
    vectors: "np.ndarray",
    alphas: "np.ndarray",
    steps: "np.ndarray",
    bits: int,
) -> "np.ndarray":
    """Vectorized quantization of a matrix of vectors.

    Args:
        vectors: (n, dim) float32 array of normalized vectors
        alphas: (dim,) per-dimension alpha values
        steps: (dim,) per-dimension step sizes
        bits: 4 or 8

    Returns:
        (n, dim) uint8 array of quantization codes.
    """
    max_int = (2 ** bits) - 1
    clipped = np.clip(vectors, -alphas, alphas)
    codes = np.round((clipped + alphas) / steps).astype(np.int32)
    codes = np.clip(codes, 0, max_int).astype(np.uint8)
    return codes


def _build_numpy_matrix(store: MemoryStore, ids: List[str]) -> "np.ndarray":
    """Build a (n, dim) float32 matrix of normalized embeddings."""
    rows = [store.embeddings[mid].normalized_f32 for mid in ids]
    return np.array(rows, dtype=np.float32)


def _build_numpy_quant_codes(
    store: MemoryStore,
    quantizer: CalibratedScalarQuantizer,
    ids: List[str],
) -> "np.ndarray":
    """Unpack all quantized codes into an (n, dim) uint8 matrix."""
    rows = []
    for mid in ids:
        qrec = store.quantized[mid]
        codes = quantizer.unpack_codes(qrec.packed_codes, qrec.embedding_dim)
        rows.append(codes)
    return np.array(rows, dtype=np.uint8)


def numpy_score_compressed(
    query_normed: List[float],
    code_matrix: "np.ndarray",
    alphas: "np.ndarray",
    steps: "np.ndarray",
) -> "np.ndarray":
    """Score query against all compressed codes using numpy.

    Reconstructs: val_j = -alpha_j + code_j * step_j
    Then dot product with query.
    """
    # code_matrix: (n, dim) uint8, alphas: (dim,), steps: (dim,)
    reconstructed = -alphas + code_matrix.astype(np.float32) * steps  # (n, dim)
    q = np.asarray(query_normed, dtype=np.float32)
    return reconstructed @ q


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

@dataclass
class StageTiming:
    embed_ms: float = 0.0
    stage1_ms: float = 0.0
    stage2_ms: float = 0.0
    total_ms: float = 0.0


def _ms(seconds: float) -> float:
    return seconds * 1000.0


def percentile(values: List[float], p: float) -> float:
    """Simple percentile (nearest-rank)."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(math.ceil(p / 100.0 * len(s))) - 1))
    return s[k]


# ---------------------------------------------------------------------------
# Instrumented retrieval -- pure Python path
# ---------------------------------------------------------------------------

def timed_retrieve_pure(
    retriever: MemoryRetriever,
    query_text: str,
    k: int = 5,
    n_candidates: int = 10,
) -> Tuple[List, StageTiming]:
    """Run the full retrieval pipeline with per-stage timing (pure Python)."""

    t0 = time.perf_counter()
    query_vec = retriever.embedder.embed_text(query_text)
    query_normed, _ = normalize(query_vec)
    t1 = time.perf_counter()

    candidates = retriever._compressed_candidate_search(query_normed, n_candidates)
    t2 = time.perf_counter()

    results = retriever._exact_rerank(query_normed, candidates, k)
    t3 = time.perf_counter()

    timing = StageTiming(
        embed_ms=_ms(t1 - t0),
        stage1_ms=_ms(t2 - t1),
        stage2_ms=_ms(t3 - t2),
        total_ms=_ms(t3 - t0),
    )
    return results, timing


# ---------------------------------------------------------------------------
# Instrumented retrieval -- numpy accelerated path
# ---------------------------------------------------------------------------

def timed_retrieve_numpy(
    retriever: MemoryRetriever,
    query_text: str,
    embed_matrix: "np.ndarray",
    code_matrix: "np.ndarray",
    np_alphas: "np.ndarray",
    np_steps: "np.ndarray",
    memory_ids: List[str],
    k: int = 5,
    n_candidates: int = 10,
) -> Tuple[List, StageTiming]:
    """Run the full retrieval pipeline using numpy acceleration."""
    from pseudocode import SearchResult

    t0 = time.perf_counter()
    query_vec = retriever.embedder.embed_text(query_text)
    query_normed, _ = normalize(query_vec)
    t1 = time.perf_counter()

    # Stage 1: compressed candidate search via numpy
    scores = numpy_score_compressed(query_normed, code_matrix, np_alphas, np_steps)
    # Get top-n_candidates indices
    if n_candidates < len(scores):
        top_indices = np.argpartition(scores, -n_candidates)[-n_candidates:]
    else:
        top_indices = np.arange(len(scores))
    # Sort the top candidates by score descending
    top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
    candidates = []
    for idx in top_indices[:n_candidates]:
        mid = memory_ids[idx]
        candidates.append(SearchResult(
            memory_id=mid,
            approx_score=float(scores[idx]),
            content=retriever.store.items[mid].content,
        ))
    t2 = time.perf_counter()

    # Stage 2: exact rerank via numpy batch score on candidates only
    cand_ids = [c.memory_id for c in candidates]
    cand_embeds = np.array(
        [retriever.store.embeddings[mid].normalized_f32 for mid in cand_ids],
        dtype=np.float32,
    )
    exact_scores = numpy_batch_score(query_normed, cand_embeds)
    reranked = []
    for i, cand in enumerate(candidates):
        reranked.append(SearchResult(
            memory_id=cand.memory_id,
            approx_score=cand.approx_score,
            exact_score=float(exact_scores[i]),
            content=cand.content,
        ))
    reranked.sort(key=lambda r: r.exact_score if r.exact_score is not None else -1e9, reverse=True)
    t3 = time.perf_counter()

    timing = StageTiming(
        embed_ms=_ms(t1 - t0),
        stage1_ms=_ms(t2 - t1),
        stage2_ms=_ms(t3 - t2),
        total_ms=_ms(t3 - t0),
    )
    return reranked[:k], timing


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    corpus_size: int
    bits: int
    backend: str  # "pure_python" or "numpy"
    num_queries: int
    timings: List[StageTiming] = field(default_factory=list)

    def _extract(self, attr: str) -> List[float]:
        return [getattr(t, attr) for t in self.timings]

    def summary(self) -> Dict:
        n_memories = self.corpus_size
        embed = self._extract("embed_ms")
        s1 = self._extract("stage1_ms")
        s2 = self._extract("stage2_ms")
        total = self._extract("total_ms")

        total_p50 = percentile(total, 50)
        qps = 1000.0 / total_p50 if total_p50 > 0 else float("inf")

        return {
            "corpus_size": n_memories,
            "bits": self.bits,
            "backend": self.backend,
            "num_queries": self.num_queries,
            "embed_ms": {"p50": percentile(embed, 50), "p95": percentile(embed, 95), "p99": percentile(embed, 99)},
            "stage1_ms": {"p50": percentile(s1, 50), "p95": percentile(s1, 95), "p99": percentile(s1, 99)},
            "stage2_ms": {"p50": percentile(s2, 50), "p95": percentile(s2, 95), "p99": percentile(s2, 99)},
            "total_ms": {"p50": total_p50, "p95": percentile(total, 95), "p99": percentile(total, 99)},
            "per_memory_score_us": (percentile(s1, 50) * 1000.0) / max(1, n_memories),
            "qps": qps,
        }


QUERY_TEMPLATES = [
    "agent memory summary retrieval",
    "vector quantization and scalar compression",
    "kv cache attention latency",
    "blockchain wallet transaction risk",
    "nearest neighbor cosine rerank index",
    "compressed agent memory systems",
    "episodic memory recall for agents",
    "embedding calibration and clipping",
    "protocol risk alert monitoring",
    "candidate generation followed by reranking",
    "inference latency optimization",
    "semantic memory context window",
    "scalar quantization with 4-bit codes",
    "bridge transaction wallet monitoring",
    "cosine similarity index retrieval",
    "attention mechanism kv compression",
    "agent planner tool selection",
    "vector search nearest neighbor",
    "quantized shadow index compression",
    "memory architecture for autonomous agents",
]


def run_single_benchmark(
    corpus_size: int,
    bits: int,
    n_queries: int,
    use_numpy: bool,
    k: int = 5,
    n_candidates: int = 20,
    seed: int = 42,
) -> BenchmarkResult:
    """Run benchmark for a single (corpus_size, bits, backend) configuration."""

    store, embedder, quantizer, indexer, retriever = build_system(bits=bits)
    generate_synthetic_corpus(indexer, corpus_size, seed=seed)

    backend = "numpy" if use_numpy else "pure_python"
    result = BenchmarkResult(
        corpus_size=corpus_size,
        bits=bits,
        backend=backend,
        num_queries=n_queries,
    )

    # Pre-build numpy structures if needed
    np_embed_matrix = None
    np_code_matrix = None
    np_alphas = None
    np_steps = None
    memory_ids = None

    if use_numpy and HAS_NUMPY:
        memory_ids = store.memory_ids()
        np_embed_matrix = _build_numpy_matrix(store, memory_ids)
        np_code_matrix = _build_numpy_quant_codes(store, quantizer, memory_ids)
        assert quantizer.alphas is not None and quantizer.steps is not None
        np_alphas = np.array(quantizer.alphas, dtype=np.float32)
        np_steps = np.array(quantizer.steps, dtype=np.float32)

    # Generate query texts
    queries = [f"{QUERY_TEMPLATES[i % len(QUERY_TEMPLATES)]} sample {i}" for i in range(n_queries)]

    # Warm up: 2 queries to fill caches
    for q in queries[:min(2, len(queries))]:
        if use_numpy and HAS_NUMPY:
            timed_retrieve_numpy(
                retriever, q, np_embed_matrix, np_code_matrix,
                np_alphas, np_steps, memory_ids, k=k, n_candidates=n_candidates,
            )
        else:
            timed_retrieve_pure(retriever, q, k=k, n_candidates=n_candidates)

    # Timed runs
    for q in queries:
        if use_numpy and HAS_NUMPY:
            _, timing = timed_retrieve_numpy(
                retriever, q, np_embed_matrix, np_code_matrix,
                np_alphas, np_steps, memory_ids, k=k, n_candidates=n_candidates,
            )
        else:
            _, timing = timed_retrieve_pure(retriever, q, k=k, n_candidates=n_candidates)
        result.timings.append(timing)

    return result


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_table(results: List[Dict]) -> str:
    """Render a human-readable latency table."""
    header = (
        f"{'Corpus':>7} | {'Bits':>4} | {'Backend':>12} | "
        f"{'Stage1 p50/p95':>18} | {'Stage2 p50/p95':>18} | "
        f"{'Total p50/p95':>18} | {'QPS':>8}"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for r in results:
        s1 = r["stage1_ms"]
        s2 = r["stage2_ms"]
        t = r["total_ms"]
        line = (
            f"{r['corpus_size']:>7} | {r['bits']:>4} | {r['backend']:>12} | "
            f"{s1['p50']:>6.1f}ms / {s1['p95']:>6.1f}ms | "
            f"{s2['p50']:>6.1f}ms / {s2['p95']:>6.1f}ms | "
            f"{t['p50']:>6.1f}ms / {t['p95']:>6.1f}ms | "
            f"{r['qps']:>8.0f}"
        )
        lines.append(line)
    return "\n".join(lines)


def format_detailed(results: List[Dict]) -> str:
    """Render a detailed per-configuration report."""
    lines = []
    for r in results:
        lines.append(f"\n--- Corpus={r['corpus_size']}  Bits={r['bits']}  Backend={r['backend']} ---")
        lines.append(f"  Queries:            {r['num_queries']}")
        for stage_name in ("embed_ms", "stage1_ms", "stage2_ms", "total_ms"):
            s = r[stage_name]
            label = stage_name.replace("_ms", "").replace("_", " ").title()
            lines.append(f"  {label:20s}  p50={s['p50']:.2f}ms  p95={s['p95']:.2f}ms  p99={s['p99']:.2f}ms")
        lines.append(f"  Per-memory score:   {r['per_memory_score_us']:.2f} us (amortized)")
        lines.append(f"  Throughput:         {r['qps']:.0f} queries/sec")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Latency benchmark for compressed agent memory retrieval"
    )
    parser.add_argument(
        "--sizes",
        type=str,
        default="100,1000,5000,10000",
        help="Comma-separated corpus sizes (default: 100,1000,5000,10000)",
    )
    parser.add_argument(
        "--bits",
        type=str,
        default="4,8",
        help="Comma-separated bit widths to test (default: 4,8)",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=20,
        help="Number of queries per configuration (default: 20)",
    )
    parser.add_argument(
        "--numpy",
        action="store_true",
        default=False,
        help="Enable numpy-accelerated path (compared alongside pure Python)",
    )
    parser.add_argument(
        "--numpy-only",
        action="store_true",
        default=False,
        help="Run only the numpy path (skip pure Python)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of final results to return (default: 5)",
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=20,
        help="Number of stage-1 candidates (default: 20)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Path for JSON report output",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for corpus generation (default: 42)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    bits_list = [int(b.strip()) for b in args.bits.split(",")]

    run_pure = not args.numpy_only
    run_numpy = args.numpy or args.numpy_only

    if run_numpy and not HAS_NUMPY:
        print("WARNING: numpy not available, falling back to pure-Python only")
        run_numpy = False
        run_pure = True

    backends: List[Tuple[str, bool]] = []
    if run_pure:
        backends.append(("pure_python", False))
    if run_numpy:
        backends.append(("numpy", True))

    all_summaries: List[Dict] = []
    total_configs = len(sizes) * len(bits_list) * len(backends)
    done = 0

    for corpus_size in sizes:
        for bits in bits_list:
            for backend_name, use_np in backends:
                done += 1
                print(
                    f"[{done}/{total_configs}] corpus={corpus_size}  bits={bits}  "
                    f"backend={backend_name} ...",
                    end="",
                    flush=True,
                )
                t_start = time.perf_counter()
                result = run_single_benchmark(
                    corpus_size=corpus_size,
                    bits=bits,
                    n_queries=args.queries,
                    use_numpy=use_np,
                    k=args.k,
                    n_candidates=args.candidates,
                    seed=args.seed,
                )
                elapsed = time.perf_counter() - t_start
                summary = result.summary()
                all_summaries.append(summary)
                print(f"  done ({elapsed:.1f}s)")

    # Print results
    print("\n" + "=" * 80)
    print("LATENCY BENCHMARK RESULTS")
    print("=" * 80)
    print()
    print(format_table(all_summaries))
    print()
    print(format_detailed(all_summaries))

    # JSON output
    report = {
        "benchmark": "mnemonic_latency",
        "config": {
            "sizes": sizes,
            "bits": bits_list,
            "queries_per_config": args.queries,
            "k": args.k,
            "n_candidates": args.candidates,
            "seed": args.seed,
            "numpy_available": HAS_NUMPY,
        },
        "results": all_summaries,
    }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"\nJSON report written to: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
