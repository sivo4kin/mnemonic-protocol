import unittest
from mnemonic.embedders import MockEmbeddingProvider
from mnemonic.indexer import MemoryIndexer
from mnemonic.quantizer import CalibratedScalarQuantizer
from mnemonic.retriever import MemoryRetriever
from mnemonic.store import MemoryStore


def build_system(dim=64, bits=8, salt=""):
    store = MemoryStore()
    embedder = MockEmbeddingProvider(dim=dim, salt=salt)
    quantizer = CalibratedScalarQuantizer(bits=bits)
    indexer = MemoryIndexer(store, embedder, quantizer)
    retriever = MemoryRetriever(store, embedder, quantizer)
    return store, embedder, quantizer, indexer, retriever


class TestMemoryRetriever(unittest.TestCase):
    def setUp(self):
        self.store, self.embedder, self.quantizer, self.indexer, self.retriever = build_system()
        # Ingest 10 items
        for i in range(10):
            self.indexer.ingest_memory(f"m{i}", f"memory item number {i} with unique content for testing retrieval")
        self.indexer.rebuild_quantized_index()

    def test_exact_search_returns_k_results(self):
        results = self.retriever.exact_search("memory retrieval", k=3)
        self.assertEqual(len(results), 3)

    def test_exact_search_sorted_by_score(self):
        results = self.retriever.exact_search("memory retrieval", k=5)
        scores = [r.exact_score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_retrieve_returns_k_results(self):
        results = self.retriever.retrieve("memory retrieval", k=3, n_candidates=5)
        self.assertEqual(len(results), 3)

    def test_compressed_candidates_returns_n(self):
        results = self.retriever.compressed_candidates("memory retrieval", n_candidates=5)
        self.assertEqual(len(results), 5)

    def test_compressed_candidates_fewer_than_store(self):
        results = self.retriever.compressed_candidates("memory retrieval", n_candidates=20)
        # Store only has 10 items, so should return at most 10
        self.assertLessEqual(len(results), 10)

    def test_targeted_query_returns_relevant_result(self):
        store, embedder, quantizer, indexer, retriever = build_system(dim=128)
        # Ingest clearly distinct topics
        indexer.ingest_memory("blockchain_1", "blockchain wallet transaction protocol risk bridge alert")
        indexer.ingest_memory("blockchain_2", "blockchain transaction risk wallet protocol")
        indexer.ingest_memory("quant_1", "quantization compression vector embedding scalar clip calibration")
        indexer.ingest_memory("quant_2", "vector quantization scalar compression embedding calibration")
        indexer.ingest_memory("memory_1", "agent memory context recall summary episodic semantic")
        indexer.rebuild_quantized_index()

        results = retriever.retrieve("blockchain wallet transaction", k=2, n_candidates=5)
        top_ids = [r.memory_id for r in results]
        # At least one blockchain item should be in top 2
        blockchain_ids = {"blockchain_1", "blockchain_2"}
        self.assertTrue(len(set(top_ids) & blockchain_ids) >= 1)

    def test_retrieve_results_sorted(self):
        results = self.retriever.retrieve("memory retrieval", k=5, n_candidates=8)
        scores = [r.exact_score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
