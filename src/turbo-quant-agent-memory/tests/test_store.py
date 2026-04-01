import unittest
from mnemonic.store import MemoryStore
from mnemonic.models import MemoryItem, EmbeddingRecord, QuantizedRecord


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def test_put_and_get_item(self):
        item = MemoryItem("m1", "hello world")
        self.store.put_item(item)
        self.assertIn("m1", self.store.items)
        self.assertEqual(self.store.items["m1"].content, "hello world")

    def test_put_embedding(self):
        rec = EmbeddingRecord(
            memory_id="m1",
            embedding_model="mock",
            embedding_dim=4,
            embedding_f32=[1.0, 2.0, 3.0, 4.0],
            embedding_norm=5.477,
            normalized_f32=[0.182, 0.365, 0.548, 0.730],
        )
        self.store.put_embedding(rec)
        self.assertIn("m1", self.store.embeddings)

    def test_put_quantized(self):
        qrec = QuantizedRecord(
            memory_id="m1",
            quant_bits=8,
            quant_scheme="symmetric",
            packed_codes=b"\x80\x80\x80\x80",
            embedding_dim=4,
        )
        self.store.put_quantized(qrec)
        self.assertIn("m1", self.store.quantized)

    def test_memory_ids_empty(self):
        self.assertEqual(self.store.memory_ids(), [])

    def test_memory_ids_after_put(self):
        self.store.put_item(MemoryItem("m1", "a"))
        self.store.put_item(MemoryItem("m2", "b"))
        ids = self.store.memory_ids()
        self.assertIn("m1", ids)
        self.assertIn("m2", ids)
        self.assertEqual(len(ids), 2)

    def test_put_item_overwrite(self):
        self.store.put_item(MemoryItem("m1", "original"))
        self.store.put_item(MemoryItem("m1", "updated"))
        self.assertEqual(self.store.items["m1"].content, "updated")


if __name__ == "__main__":
    unittest.main()
