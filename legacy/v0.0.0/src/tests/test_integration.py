import tempfile
import unittest
from pathlib import Path

from mnemonic.embedders import MockEmbeddingProvider
from mnemonic.indexer import MemoryIndexer
from mnemonic.persistence import save_to_sqlite, load_from_sqlite, snapshot_items, restore_from_snapshot
from mnemonic.quantizer import CalibratedScalarQuantizer
from mnemonic.retriever import MemoryRetriever
from mnemonic.store import MemoryStore


SYNTHETIC_MEMORIES = [
    ("quant_1", "quantization compression vector embedding scalar clip calibration"),
    ("quant_2", "vector scalar quantization compression calibration embedding"),
    ("quant_3", "scalar quantizer calibration clip embedding compression"),
    ("quant_4", "quantization embedding vector scalar compression"),
    ("mem_1", "agent memory context recall summary episodic semantic"),
    ("mem_2", "memory recall episodic semantic agent context summary"),
    ("mem_3", "agent episodic memory recall context semantic"),
    ("mem_4", "semantic memory agent recall episodic context"),
    ("llm_1", "llm kv cache attention latency inference context"),
    ("llm_2", "kv cache attention llm latency inference"),
    ("llm_3", "attention cache llm kv inference latency"),
    ("llm_4", "llm inference attention kv cache latency"),
    ("chain_1", "blockchain wallet transaction protocol risk bridge alert"),
    ("chain_2", "wallet transaction blockchain protocol risk alert"),
    ("chain_3", "protocol risk blockchain wallet transaction bridge"),
    ("chain_4", "blockchain transaction risk wallet protocol alert"),
    ("search_1", "nearest neighbor rerank candidate cosine index retrieval"),
    ("search_2", "cosine similarity nearest neighbor rerank candidate"),
    ("search_3", "candidate retrieval nearest neighbor cosine rerank"),
    ("search_4", "rerank index nearest neighbor candidate cosine retrieval"),
]


def build_system(dim=64, bits=8):
    store = MemoryStore()
    embedder = MockEmbeddingProvider(dim=dim)
    quantizer = CalibratedScalarQuantizer(bits=bits)
    indexer = MemoryIndexer(store, embedder, quantizer)
    retriever = MemoryRetriever(store, embedder, quantizer)
    return store, embedder, quantizer, indexer, retriever


class TestIntegration(unittest.TestCase):
    def test_full_pipeline(self):
        store, embedder, quantizer, indexer, retriever = build_system(dim=128, bits=8)

        # Step 1: Ingest 20 synthetic memories
        for mid, content in SYNTHETIC_MEMORIES:
            indexer.ingest_memory(mid, content)
        indexer.rebuild_quantized_index()
        self.assertEqual(len(store.memory_ids()), 20)

        # Step 2: Run retrieve on targeted query
        results = retriever.retrieve("quantization compression vector scalar", k=3, n_candidates=10)
        top_ids = [r.memory_id for r in results]
        quant_ids = {"quant_1", "quant_2", "quant_3", "quant_4"}
        self.assertTrue(len(set(top_ids) & quant_ids) >= 1, f"Expected quant result in top 3, got {top_ids}")

        # Step 3: Save to SQLite, reload, run same queries
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            db_path = Path(tmp.name)
        try:
            save_to_sqlite(store, quantizer, db_path)
            store2, quantizer2 = load_from_sqlite(db_path)
        finally:
            db_path.unlink(missing_ok=True)

        retriever2 = MemoryRetriever(store2, embedder, quantizer2)
        results2 = retriever2.retrieve("quantization compression vector scalar", k=3, n_candidates=10)
        top_ids2 = [r.memory_id for r in results2]

        # Results should be identical after reload
        self.assertEqual(top_ids, top_ids2, f"Results differ after SQLite reload: {top_ids} vs {top_ids2}")

        # Step 4: Snapshot -> restore with different salt -> recall >= 0.7 of baseline
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            snap_path = Path(tmp.name)
        try:
            snapshot_items(store, snap_path)
            store3 = MemoryStore()
            embedder3 = MockEmbeddingProvider(dim=128, salt="different_salt")
            quantizer3 = CalibratedScalarQuantizer(bits=8)
            indexer3 = MemoryIndexer(store3, embedder3, quantizer3)
            retriever3 = MemoryRetriever(store3, embedder3, quantizer3)
            restore_from_snapshot(snap_path, indexer3)
        finally:
            snap_path.unlink(missing_ok=True)

        # Measure recall: how many of baseline top-k appear in new top-k
        test_queries = [
            ("quantization compression vector scalar", quant_ids),
            ("blockchain wallet transaction protocol", {"chain_1", "chain_2", "chain_3", "chain_4"}),
            ("agent memory recall episodic", {"mem_1", "mem_2", "mem_3", "mem_4"}),
        ]
        hits = 0
        total = 0
        for query, relevant in test_queries:
            r_base = retriever.retrieve(query, k=3, n_candidates=10)
            r_new = retriever3.retrieve(query, k=3, n_candidates=10)
            base_ids = set(r.memory_id for r in r_base)
            new_ids = set(r.memory_id for r in r_new)
            hits += len(base_ids & new_ids)
            total += len(base_ids)

        recall = hits / max(total, 1)
        self.assertGreaterEqual(recall, 0.7, f"Recall after provider switch too low: {recall:.3f}")


if __name__ == "__main__":
    unittest.main()
