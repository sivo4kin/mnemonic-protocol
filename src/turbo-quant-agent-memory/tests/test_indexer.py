import unittest
from mnemonic.embedders import MockEmbeddingProvider
from mnemonic.indexer import MemoryIndexer
from mnemonic.quantizer import CalibratedScalarQuantizer
from mnemonic.store import MemoryStore


class TestMemoryIndexer(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.embedder = MockEmbeddingProvider(dim=64)
        self.quantizer = CalibratedScalarQuantizer(bits=8)
        self.indexer = MemoryIndexer(self.store, self.embedder, self.quantizer)

    def test_ingest_memory_adds_item_to_store(self):
        self.indexer.ingest_memory("m1", "agent memory quantization")
        self.assertIn("m1", self.store.items)
        self.assertIn("m1", self.store.embeddings)

    def test_ingest_memory_stores_embedding(self):
        self.indexer.ingest_memory("m1", "hello world")
        emb = self.store.embeddings["m1"]
        self.assertEqual(emb.embedding_dim, 64)
        self.assertEqual(len(emb.embedding_f32), 64)
        self.assertEqual(len(emb.normalized_f32), 64)

    def test_ingest_memory_custom_fields(self):
        self.indexer.ingest_memory("m1", "content", memory_type="semantic", importance_score=0.7, tags=["a", "b"])
        item = self.store.items["m1"]
        self.assertEqual(item.memory_type, "semantic")
        self.assertEqual(item.importance_score, 0.7)
        self.assertEqual(item.tags, ["a", "b"])

    def test_rebuild_quantized_index_populates_quantized(self):
        for i in range(5):
            self.indexer.ingest_memory(f"m{i}", f"memory about topic {i} quantization agent")
        self.indexer.rebuild_quantized_index()
        ids = self.store.memory_ids()
        self.assertEqual(len(ids), 5)
        for mid in ids:
            self.assertIn(mid, self.store.quantized)

    def test_rebuild_quantized_index_empty_store(self):
        # Should not raise
        self.indexer.rebuild_quantized_index()

    def test_quantizer_fit_after_rebuild(self):
        for i in range(3):
            self.indexer.ingest_memory(f"m{i}", f"content {i}")
        self.indexer.rebuild_quantized_index()
        self.assertTrue(self.quantizer.is_fit())


if __name__ == "__main__":
    unittest.main()
