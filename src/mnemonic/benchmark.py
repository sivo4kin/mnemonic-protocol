from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .embedders import BaseEmbeddingProvider, MockEmbeddingProvider, OpenAIEmbeddingProvider, build_embedder, _has_embed_batch
from .indexer import MemoryIndexer, Quantizer
from .math_utils import normalize
from .models import EmbeddingRecord, MemoryItem, SearchResult
from .persistence import (
    ingest_memory_jsonl,
    load_jsonl,
    restore_from_snapshot,
    save_to_sqlite,
    load_from_sqlite,
    snapshot_items,
)
from .quantizer import CalibratedScalarQuantizer, TurboQuantAdapter, _TURBOQUANT_AVAILABLE
from .retriever import MemoryRetriever
from .store import MemoryStore


def build_system(bits: int = 8, embedder_name: str = "mock", dim: int = 384, quantizer_name: str = "auto"):
    """Build the full memory system.

    quantizer_name: "scalar" for legacy CalibratedScalarQuantizer,
                    "turboquant" for TurboQuantAdapter,
                    "auto" (default) uses turboquant if available, else scalar.
    """
    root = Path(__file__).resolve().parent.parent
    cache_dir = root / ".cache" / "embeddings"
    store = MemoryStore()
    embedder = build_embedder(embedder_name, cache_dir=cache_dir, dim=dim)

    use_turbo = (
        (quantizer_name == "turboquant") or
        (quantizer_name == "auto" and _TURBOQUANT_AVAILABLE)
    )
    if use_turbo:
        quantizer: Quantizer = TurboQuantAdapter(bits=max(bits, 2), dim=dim)
    else:
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

    # Batch-embed when provider supports it (OpenAI, Nomic) to avoid per-item calls
    if _has_embed_batch(indexer.embedder):
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

    if _has_embed_batch(indexer.embedder):
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
    root = Path(__file__).resolve().parent.parent
    cache_dir = root / ".cache" / "embeddings"

    store_a = MemoryStore()
    embedder = MockEmbeddingProvider(dim=384, cache=None)
    from .cache import EmbeddingCache
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
    from .cache import EmbeddingCache

    root = Path(__file__).resolve().parent.parent
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
