"""Compatibility shim — all logic lives in the mnemonic package."""
from mnemonic import *  # noqa: F401,F403
from mnemonic import (
    MemoryItem, EmbeddingRecord, QuantizedRecord, SearchResult,
    dot, l2_norm, normalize, clip,
    EmbeddingCache,
    BaseEmbeddingProvider, MockEmbeddingProvider, OpenAIEmbeddingProvider, build_embedder,
    CalibratedScalarQuantizer,
    MemoryStore, MemoryIndexer, MemoryRetriever,
    load_jsonl, ingest_memory_jsonl,
    save_to_sqlite, load_from_sqlite,
    snapshot_items, restore_from_snapshot,
    build_system, generate_synthetic_corpus, recall_at_k,
    estimate_index_bytes, quant_diagnostics,
    run_benchmark, run_multidomain_benchmark,
    run_persist_test, run_provider_switch_test,
)
from mnemonic.__main__ import parse_args, main
import sys

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
