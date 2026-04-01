"""
Mnemonic MVP: Verify that compressed agent memory survives an on-chain round-trip.

End-to-end pipeline:
  1. Ingest memories → embed → compress
  2. Run baseline retrieval
  3. Serialize entire memory state to a binary blob
  4. Hash blob (SHA3-256) — this is the on-chain commitment
  5. Rehydrate from blob
  6. Run retrieval on rehydrated state
  7. Compare: baseline vs rehydrated results must be identical

Usage:
  python mvp_verify.py                           # quick test with 100 synthetic memories
  python mvp_verify.py --memories 10000 --bits 4  # stress test
  python mvp_verify.py --memory-file corpus.jsonl --query-file queries.jsonl
  python mvp_verify.py --out results.json         # save metrics
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mnemonic import (
    BaseEmbeddingProvider,
    CalibratedScalarQuantizer,
    EmbeddingRecord,
    MemoryItem,
    MemoryStore,
    MemoryIndexer,
    MemoryRetriever,
    QuantizedRecord,
    SearchResult,
    build_embedder,
    generate_synthetic_corpus,
    ingest_memory_jsonl,
    load_jsonl,
    recall_at_k,
    estimate_index_bytes,
    quant_diagnostics,
    normalize,
    dot,
)


# ---------------------------------------------------------------------------
# Serialization: memory state → binary blob
# ---------------------------------------------------------------------------

BLOB_MAGIC = b"MNEM"
BLOB_VERSION = 1


def serialize_snapshot(
    store: MemoryStore,
    quantizer: CalibratedScalarQuantizer,
    embedding_model: str,
) -> bytes:
    """Pack entire memory state into a deterministic binary blob."""
    memory_ids = sorted(store.memory_ids())  # canonical order
    if not memory_ids:
        raise ValueError("Nothing to serialize — store is empty")

    sample_emb = store.embeddings[memory_ids[0]]
    dim = sample_emb.embedding_dim
    n = len(memory_ids)

    parts: list[bytes] = []

    # -- Header (fixed size: 64 bytes) --
    model_bytes = embedding_model.encode("utf-8")[:32].ljust(32, b"\x00")
    header = struct.pack(
        "<4sH32sHBxI16x",  # 4+2+32+2+1+1+4+16 = 62 ... pad to 64
        BLOB_MAGIC,
        BLOB_VERSION,
        model_bytes,
        dim,
        quantizer.bits,
        n,
    )
    header = header.ljust(64, b"\x00")
    parts.append(header)

    # -- Quantizer state --
    assert quantizer.alphas is not None and quantizer.steps is not None
    parts.append(struct.pack(f"<{dim}f", *quantizer.alphas))
    parts.append(struct.pack(f"<{dim}f", *quantizer.steps))

    # -- Per-memory records (deterministic order) --
    for mid in memory_ids:
        item = store.items[mid]
        emb = store.embeddings[mid]
        qrec = store.quantized[mid]

        # memory_id (length-prefixed utf-8)
        mid_bytes = mid.encode("utf-8")
        parts.append(struct.pack("<H", len(mid_bytes)))
        parts.append(mid_bytes)

        # text content (length-prefixed utf-8)
        text_bytes = item.content.encode("utf-8")
        parts.append(struct.pack("<I", len(text_bytes)))
        parts.append(text_bytes)

        # metadata as JSON (length-prefixed)
        meta = {
            "memory_type": item.memory_type,
            "importance_score": item.importance_score,
            "tags": item.tags,
        }
        meta_bytes = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
        parts.append(struct.pack("<H", len(meta_bytes)))
        parts.append(meta_bytes)

        # embedding norm
        parts.append(struct.pack("<f", emb.embedding_norm))

        # full-precision normalized embedding
        parts.append(struct.pack(f"<{dim}f", *emb.normalized_f32))

        # compressed codes
        parts.append(struct.pack("<H", len(qrec.packed_codes)))
        parts.append(qrec.packed_codes)

    # -- Footer --
    parts.append(struct.pack("<I", n))  # record count for integrity

    return b"".join(parts)


def deserialize_snapshot(blob: bytes) -> Tuple[MemoryStore, CalibratedScalarQuantizer, str]:
    """Unpack a binary blob back into a full memory state."""
    offset = 0

    def read(size: int) -> bytes:
        nonlocal offset
        data = blob[offset : offset + size]
        if len(data) < size:
            raise ValueError(f"Blob truncated at offset {offset}, expected {size} bytes")
        offset += size
        return data

    # -- Header --
    header = read(64)
    magic, version, model_raw, dim, bits, n = struct.unpack_from("<4sH32sHBxI", header)
    if magic != BLOB_MAGIC:
        raise ValueError(f"Bad magic: {magic}")
    if version != BLOB_VERSION:
        raise ValueError(f"Unsupported blob version: {version}")
    embedding_model = model_raw.rstrip(b"\x00").decode("utf-8")

    # -- Quantizer state --
    alphas = list(struct.unpack(f"<{dim}f", read(dim * 4)))
    steps = list(struct.unpack(f"<{dim}f", read(dim * 4)))

    quantizer = CalibratedScalarQuantizer(bits=bits)
    quantizer.alphas = alphas
    quantizer.steps = steps

    # -- Records --
    store = MemoryStore()

    for _ in range(n):
        # memory_id
        (mid_len,) = struct.unpack("<H", read(2))
        mid = read(mid_len).decode("utf-8")

        # text
        (text_len,) = struct.unpack("<I", read(4))
        text = read(text_len).decode("utf-8")

        # metadata
        (meta_len,) = struct.unpack("<H", read(2))
        meta = json.loads(read(meta_len).decode("utf-8"))

        # norm
        (norm,) = struct.unpack("<f", read(4))

        # full embedding
        normalized = list(struct.unpack(f"<{dim}f", read(dim * 4)))

        # compressed codes
        (codes_len,) = struct.unpack("<H", read(2))
        packed_codes = read(codes_len)

        # Reconstruct full embedding from normalized + norm
        full_emb = [x * norm for x in normalized]

        store.put_item(MemoryItem(
            memory_id=mid,
            content=text,
            memory_type=meta.get("memory_type", "episodic"),
            importance_score=meta.get("importance_score", 0.0),
            tags=meta.get("tags", []),
        ))
        store.put_embedding(EmbeddingRecord(
            memory_id=mid,
            embedding_model=embedding_model,
            embedding_dim=dim,
            embedding_f32=full_emb,
            embedding_norm=norm,
            normalized_f32=normalized,
        ))

        # Recompute saturation rate from codes
        codes = quantizer.unpack_codes(packed_codes, dim)
        saturated = sum(1 for c in codes if c == 0 or c == quantizer.max_int)
        sat_rate = saturated / max(1, dim)

        store.put_quantized(QuantizedRecord(
            memory_id=mid,
            quant_bits=bits,
            quant_scheme="symmetric_uniform_per_dim_calibrated",
            packed_codes=packed_codes,
            embedding_dim=dim,
            saturation_rate=sat_rate,
        ))

    # -- Footer --
    (footer_n,) = struct.unpack("<I", read(4))
    if footer_n != n:
        raise ValueError(f"Footer mismatch: header says {n}, footer says {footer_n}")

    return store, quantizer, embedding_model


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha3_256(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


# ---------------------------------------------------------------------------
# Retrieval comparison
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    query: str
    candidate_ids: List[str]
    final_ids: List[str]
    candidate_scores: List[float]
    final_scores: List[float]


def run_retrieval_suite(
    store: MemoryStore,
    embedder: BaseEmbeddingProvider,
    quantizer: CalibratedScalarQuantizer,
    queries: List[str],
    k: int,
    n_candidates: int,
) -> List[QueryResult]:
    retriever = MemoryRetriever(store, embedder, quantizer)
    results = []
    for q in queries:
        candidates = retriever.compressed_candidates(q, n_candidates=n_candidates)
        final = retriever.retrieve(q, k=k, n_candidates=n_candidates)
        results.append(QueryResult(
            query=q,
            candidate_ids=[r.memory_id for r in candidates],
            final_ids=[r.memory_id for r in final],
            candidate_scores=[r.approx_score for r in candidates],
            final_scores=[r.exact_score for r in final if r.exact_score is not None],
        ))
    return results


def compare_results(baseline: List[QueryResult], rehydrated: List[QueryResult]) -> dict:
    """Compare two retrieval runs. Returns detailed comparison."""
    assert len(baseline) == len(rehydrated)

    candidate_matches = 0
    final_matches = 0
    total = len(baseline)
    diffs = []

    for i, (b, r) in enumerate(zip(baseline, rehydrated)):
        cand_match = b.candidate_ids == r.candidate_ids
        final_match = b.final_ids == r.final_ids

        if cand_match:
            candidate_matches += 1
        if final_match:
            final_matches += 1

        if not cand_match or not final_match:
            diffs.append({
                "query_index": i,
                "query": b.query,
                "candidates_match": cand_match,
                "finals_match": final_match,
                "baseline_candidates": b.candidate_ids[:5],
                "rehydrated_candidates": r.candidate_ids[:5],
                "baseline_finals": b.final_ids,
                "rehydrated_finals": r.final_ids,
            })

    return {
        "total_queries": total,
        "candidate_set_identical": candidate_matches,
        "final_set_identical": final_matches,
        "candidate_match_rate": candidate_matches / max(1, total),
        "final_match_rate": final_matches / max(1, total),
        "all_identical": candidate_matches == total and final_matches == total,
        "diffs": diffs[:10],  # cap for readability
    }


# ---------------------------------------------------------------------------
# Retrieval quality (recall vs exact baseline)
# ---------------------------------------------------------------------------

def measure_recall(
    store: MemoryStore,
    embedder: BaseEmbeddingProvider,
    quantizer: CalibratedScalarQuantizer,
    queries: List[str],
    k: int,
    n_candidates: int,
) -> dict:
    retriever = MemoryRetriever(store, embedder, quantizer)
    candidate_recalls = []
    final_recalls = []

    for q in queries:
        exact = retriever.exact_search(q, k=k)
        exact_ids = [r.memory_id for r in exact]

        candidates = retriever.compressed_candidates(q, n_candidates=n_candidates)
        final = retriever.retrieve(q, k=k, n_candidates=n_candidates)

        candidate_ids = [r.memory_id for r in candidates]
        final_ids = [r.memory_id for r in final]

        candidate_recalls.append(recall_at_k(candidate_ids, exact_ids, k))
        final_recalls.append(recall_at_k(final_ids, exact_ids, k))

    return {
        "avg_candidate_recall_at_k": sum(candidate_recalls) / max(1, len(candidate_recalls)),
        "avg_final_recall_at_k": sum(final_recalls) / max(1, len(final_recalls)),
        "min_candidate_recall": min(candidate_recalls) if candidate_recalls else 0,
        "min_final_recall": min(final_recalls) if final_recalls else 0,
    }


# ---------------------------------------------------------------------------
# Synthetic query generation
# ---------------------------------------------------------------------------

def generate_queries(n: int, seed: int = 42) -> List[str]:
    random.seed(seed)
    templates = [
        "agent memory {topic} retrieval",
        "vector {topic} compression methods",
        "{topic} cache latency optimization",
        "blockchain {topic} transaction monitoring",
        "nearest neighbor {topic} reranking",
        "{topic} systems architecture design",
        "compressed {topic} index search",
        "scalable {topic} quantization approach",
    ]
    topics = [
        "summary", "embedding", "scalar", "calibration", "wallet",
        "protocol", "cosine", "candidate", "inference", "context",
        "attention", "episodic", "semantic", "risk", "bridge",
    ]
    queries = []
    for i in range(n):
        template = random.choice(templates)
        topic = random.choice(topics)
        queries.append(template.format(topic=topic))
    return queries


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_mvp(
    bits: int = 8,
    embedder_name: str = "mock",
    n_memories: int = 100,
    n_queries: int = 50,
    k: int = 10,
    n_candidates: int = 50,
    memory_file: Optional[Path] = None,
    query_file: Optional[Path] = None,
    out_file: Optional[Path] = None,
    blob_file: Optional[Path] = None,
    dim: int = 384,
) -> dict:

    print("=" * 60)
    print("MNEMONIC MVP — On-Chain Memory Round-Trip Verification")
    print("=" * 60)

    # --- Step 1: Build and populate memory store ---
    t0 = time.time()

    root = Path(__file__).resolve().parent
    cache_dir = root / ".cache" / "embeddings"
    store = MemoryStore()
    embedder = build_embedder(embedder_name, cache_dir=cache_dir, dim=dim)
    quantizer = CalibratedScalarQuantizer(bits=bits)
    indexer = MemoryIndexer(store, embedder, quantizer)

    if memory_file is not None:
        ingest_memory_jsonl(indexer, memory_file)
        dataset_mode = "jsonl"
    else:
        generate_synthetic_corpus(indexer, n_memories)
        dataset_mode = "synthetic"

    t_ingest = time.time() - t0
    print(f"\n[1/9] INGEST: {len(store.memory_ids())} memories ingested ({t_ingest:.2f}s)")
    print(f"      embedder={embedder.provider_name()} model={embedder.model_name} bits={bits}")

    # --- Step 2: Load/generate queries ---
    if query_file is not None:
        query_rows = load_jsonl(query_file)
        queries = [r["query"] for r in query_rows[:n_queries]]
    else:
        queries = generate_queries(n_queries)

    print(f"[2/9] QUERIES: {len(queries)} test queries loaded")

    # --- Step 3: Baseline retrieval ---
    t0 = time.time()
    baseline_results = run_retrieval_suite(store, embedder, quantizer, queries, k, n_candidates)
    t_baseline = time.time() - t0
    print(f"[3/9] BASELINE: retrieval complete ({t_baseline:.2f}s)")

    # --- Step 4: Measure recall vs exact search ---
    t0 = time.time()
    recall_metrics = measure_recall(store, embedder, quantizer, queries, k, n_candidates)
    t_recall = time.time() - t0
    print(f"[4/9] RECALL: candidate={recall_metrics['avg_candidate_recall_at_k']:.4f} "
          f"final={recall_metrics['avg_final_recall_at_k']:.4f} ({t_recall:.2f}s)")

    # --- Step 5: Serialize to blob ---
    t0 = time.time()
    blob = serialize_snapshot(store, quantizer, embedder.model_name)
    t_serialize = time.time() - t0
    print(f"[5/9] SERIALIZE: {len(blob):,} bytes ({t_serialize:.2f}s)")

    # --- Step 5b: Save blob to disk if requested ---
    if blob_file is not None:
        blob_file.parent.mkdir(parents=True, exist_ok=True)
        blob_file.write_bytes(blob)
        print(f"      blob saved to: {blob_file}")

    # --- Step 6: Hash (on-chain commitment) ---
    content_hash = sha3_256(blob)
    print(f"[6/9] HASH: SHA3-256 = {content_hash[:16]}...{content_hash[-16:]}")

    # --- Step 7: Rehydrate from blob ---
    t0 = time.time()
    restored_store, restored_quantizer, restored_model = deserialize_snapshot(blob)
    t_rehydrate = time.time() - t0

    # Verify hash of re-serialized blob
    reblob = serialize_snapshot(restored_store, restored_quantizer, restored_model)
    rehash = sha3_256(reblob)
    hash_match = content_hash == rehash

    print(f"[7/9] REHYDRATE: {len(restored_store.memory_ids())} memories restored ({t_rehydrate:.2f}s)")
    print(f"      re-serialized hash match: {'PASS' if hash_match else 'FAIL'}")

    # --- Step 8: Retrieval on rehydrated state ---
    t0 = time.time()
    rehydrated_results = run_retrieval_suite(
        restored_store, embedder, restored_quantizer, queries, k, n_candidates
    )
    t_rehydrated = time.time() - t0
    print(f"[8/9] REHYDRATED RETRIEVAL: complete ({t_rehydrated:.2f}s)")

    # --- Step 9: Compare ---
    comparison = compare_results(baseline_results, rehydrated_results)

    # Storage metrics
    float_bytes, compressed_bytes = estimate_index_bytes(store)
    sat_min, sat_mean, sat_max = quant_diagnostics(store)

    # Economics estimate
    arweave_cost = len(blob) / 1e9 * 5.0  # ~$5/GB
    solana_cost = 0.00025  # ~1 tx

    print(f"\n[9/9] RESULTS")
    print(f"      ┌─────────────────────────────────────────────┐")
    print(f"      │  ROUND-TRIP VERIFICATION                    │")
    print(f"      ├─────────────────────────────────────────────┤")
    print(f"      │  Hash match (blob integrity):  {'✓ PASS' if hash_match else '✗ FAIL'}        │")
    print(f"      │  Candidate sets identical:      {comparison['candidate_match_rate']:.0%}         │")
    print(f"      │  Final results identical:       {comparison['final_match_rate']:.0%}         │")
    print(f"      │  ALL IDENTICAL:                 {'✓ PASS' if comparison['all_identical'] else '✗ FAIL'}        │")
    print(f"      ├─────────────────────────────────────────────┤")
    print(f"      │  RETRIEVAL QUALITY                          │")
    print(f"      │  Candidate recall@{k}:           {recall_metrics['avg_candidate_recall_at_k']:.4f}       │")
    print(f"      │  Final recall@{k} (post-rerank): {recall_metrics['avg_final_recall_at_k']:.4f}       │")
    print(f"      ├─────────────────────────────────────────────┤")
    print(f"      │  COMPRESSION                                │")
    print(f"      │  Blob size:                     {len(blob):>10,} B │")
    print(f"      │  Float index:                   {float_bytes:>10,} B │")
    print(f"      │  Compressed index:              {compressed_bytes:>10,} B │")
    print(f"      │  Compression ratio:             {compressed_bytes/max(1,float_bytes):>10.1%}   │")
    print(f"      ├─────────────────────────────────────────────┤")
    print(f"      │  ECONOMICS (estimated)                      │")
    print(f"      │  Arweave storage:               ${arweave_cost:>9.5f}   │")
    print(f"      │  Solana commitment:             ${solana_cost:>9.5f}   │")
    print(f"      │  Total per snapshot:            ${arweave_cost + solana_cost:>9.5f}   │")
    print(f"      └─────────────────────────────────────────────┘")

    if comparison["diffs"]:
        print(f"\n      First diff (of {len(comparison['diffs'])}):")
        d = comparison["diffs"][0]
        print(f"        query: {d['query']}")
        print(f"        baseline finals:    {d['baseline_finals']}")
        print(f"        rehydrated finals:  {d['rehydrated_finals']}")

    # --- Verdict ---
    passed = hash_match and comparison["all_identical"]
    print(f"\n{'=' * 60}")
    if passed:
        print("VERDICT: ✓ PASS — Compressed memory survives on-chain round-trip")
        print("         Retrieval is deterministic. Architecture is viable.")
    else:
        print("VERDICT: ✗ FAIL — Round-trip introduced differences")
        if not hash_match:
            print("         Serialization is non-deterministic (blob hash mismatch)")
        if not comparison["all_identical"]:
            print(f"         {comparison['total_queries'] - comparison['final_set_identical']}/{comparison['total_queries']} queries returned different results")
    print("=" * 60)

    # --- Output ---
    report = {
        "verdict": "PASS" if passed else "FAIL",
        "config": {
            "embedder": embedder.provider_name(),
            "model": embedder.model_name,
            "bits": bits,
            "k": k,
            "n_candidates": n_candidates,
            "dataset_mode": dataset_mode,
            "num_memories": len(store.memory_ids()),
            "num_queries": len(queries),
            "embedding_dim": store.embeddings[store.memory_ids()[0]].embedding_dim,
        },
        "round_trip": {
            "blob_size_bytes": len(blob),
            "content_hash": content_hash,
            "hash_match": hash_match,
            "candidate_sets_identical": comparison["candidate_match_rate"],
            "final_sets_identical": comparison["final_match_rate"],
            "all_identical": comparison["all_identical"],
        },
        "retrieval_quality": recall_metrics,
        "compression": {
            "float_index_bytes": float_bytes,
            "compressed_index_bytes": compressed_bytes,
            "compression_ratio": compressed_bytes / max(1, float_bytes),
            "quant_avg_alpha": quantizer.average_alpha(),
            "saturation_min": sat_min,
            "saturation_mean": sat_mean,
            "saturation_max": sat_max,
        },
        "economics": {
            "arweave_cost_usd": arweave_cost,
            "solana_cost_usd": solana_cost,
            "total_cost_usd": arweave_cost + solana_cost,
        },
        "timing": {
            "ingest_s": round(t_ingest, 3),
            "baseline_retrieval_s": round(t_baseline, 3),
            "serialize_s": round(t_serialize, 3),
            "rehydrate_s": round(t_rehydrate, 3),
            "rehydrated_retrieval_s": round(t_rehydrated, 3),
        },
    }

    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(report, indent=2))
        print(f"\nResults written to: {out_file}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mnemonic MVP — verify compressed memory survives on-chain round-trip"
    )
    parser.add_argument("--bits", type=int, default=8, choices=[4, 8],
                        help="Quantization bit-width (default: 8)")
    parser.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"],
                        help="Embedding provider (default: mock)")
    parser.add_argument("--memories", type=int, default=100,
                        help="Number of synthetic memories (default: 100)")
    parser.add_argument("--queries", type=int, default=50,
                        help="Number of test queries (default: 50)")
    parser.add_argument("--k", type=int, default=10,
                        help="Top-k results (default: 10)")
    parser.add_argument("--candidates", type=int, default=50,
                        help="Candidate shortlist size (default: 50)")
    parser.add_argument("--memory-file", type=Path, default=None,
                        help="JSONL file with memory items")
    parser.add_argument("--query-file", type=Path, default=None,
                        help="JSONL file with queries")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output JSON file for results")
    parser.add_argument("--save-blob", type=Path, default=None,
                        help="Save serialized blob to this path (for on-chain commitment)")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    report = run_mvp(
        bits=args.bits,
        embedder_name=args.embedder,
        n_memories=args.memories,
        n_queries=args.queries,
        k=args.k,
        n_candidates=args.candidates,
        memory_file=args.memory_file,
        query_file=args.query_file,
        out_file=args.out,
        blob_file=args.save_blob,
    )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
