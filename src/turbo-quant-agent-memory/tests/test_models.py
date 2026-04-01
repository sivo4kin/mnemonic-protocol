import unittest
from mnemonic.models import MemoryItem, EmbeddingRecord, QuantizedRecord, SearchResult


class TestMemoryItem(unittest.TestCase):
    def test_instantiate_defaults(self):
        item = MemoryItem(memory_id="m1", content="hello world")
        self.assertEqual(item.memory_id, "m1")
        self.assertEqual(item.content, "hello world")
        self.assertEqual(item.memory_type, "episodic")
        self.assertEqual(item.importance_score, 0.0)
        self.assertEqual(item.tags, [])

    def test_instantiate_custom(self):
        item = MemoryItem("m2", "content", "semantic", 0.5, ["tag1"])
        self.assertEqual(item.memory_type, "semantic")
        self.assertEqual(item.importance_score, 0.5)
        self.assertEqual(item.tags, ["tag1"])


class TestEmbeddingRecord(unittest.TestCase):
    def test_instantiate(self):
        rec = EmbeddingRecord(
            memory_id="m1",
            embedding_model="mock",
            embedding_dim=4,
            embedding_f32=[1.0, 2.0, 3.0, 4.0],
            embedding_norm=5.477,
            normalized_f32=[0.182, 0.365, 0.548, 0.730],
        )
        self.assertEqual(rec.memory_id, "m1")
        self.assertEqual(rec.embedding_dim, 4)


class TestQuantizedRecord(unittest.TestCase):
    def test_instantiate_defaults(self):
        rec = QuantizedRecord(
            memory_id="m1",
            quant_bits=8,
            quant_scheme="symmetric",
            packed_codes=b"\x01\x02",
            embedding_dim=2,
        )
        self.assertEqual(rec.saturation_rate, 0.0)
        self.assertEqual(rec.quant_bits, 8)


class TestSearchResult(unittest.TestCase):
    def test_instantiate_defaults(self):
        result = SearchResult(memory_id="m1", approx_score=0.9)
        self.assertEqual(result.memory_id, "m1")
        self.assertEqual(result.approx_score, 0.9)
        self.assertIsNone(result.exact_score)
        self.assertIsNone(result.content)

    def test_instantiate_full(self):
        result = SearchResult("m1", 0.9, 0.95, "some content")
        self.assertEqual(result.exact_score, 0.95)
        self.assertEqual(result.content, "some content")


if __name__ == "__main__":
    unittest.main()
