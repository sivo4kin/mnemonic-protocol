import json
import tempfile
import unittest
from pathlib import Path

from mnemonic.embedders import MockEmbeddingProvider
from mnemonic.indexer import MemoryIndexer
from mnemonic.persistence import (
    load_jsonl,
    ingest_memory_jsonl,
    save_to_sqlite,
    load_from_sqlite,
    snapshot_items,
    restore_from_snapshot,
)
from mnemonic.quantizer import CalibratedScalarQuantizer
from mnemonic.retriever import MemoryRetriever
from mnemonic.store import MemoryStore


def build_and_populate(n=10, dim=64, bits=8):
    store = MemoryStore()
    embedder = MockEmbeddingProvider(dim=dim)
    quantizer = CalibratedScalarQuantizer(bits=bits)
    indexer = MemoryIndexer(store, embedder, quantizer)
    for i in range(n):
        indexer.ingest_memory(f"m{i}", f"memory content {i} about quantization and retrieval")
    indexer.rebuild_quantized_index()
    return store, embedder, quantizer, indexer


class TestSaveLoadSQLite(unittest.TestCase):
    def test_roundtrip_memory_ids(self):
        store, embedder, quantizer, indexer = build_and_populate(n=5)
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            db_path = Path(tmp.name)
        try:
            save_to_sqlite(store, quantizer, db_path)
            store2, quantizer2 = load_from_sqlite(db_path)
            self.assertEqual(set(store.memory_ids()), set(store2.memory_ids()))
        finally:
            db_path.unlink(missing_ok=True)

    def test_roundtrip_content(self):
        store, embedder, quantizer, indexer = build_and_populate(n=5)
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            db_path = Path(tmp.name)
        try:
            save_to_sqlite(store, quantizer, db_path)
            store2, _ = load_from_sqlite(db_path)
            for mid in store.memory_ids():
                self.assertEqual(store.items[mid].content, store2.items[mid].content)
        finally:
            db_path.unlink(missing_ok=True)

    def test_roundtrip_quantizer_alphas(self):
        store, embedder, quantizer, indexer = build_and_populate(n=5)
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            db_path = Path(tmp.name)
        try:
            save_to_sqlite(store, quantizer, db_path)
            _, quantizer2 = load_from_sqlite(db_path)
            self.assertIsNotNone(quantizer.alphas)
            self.assertIsNotNone(quantizer2.alphas)
            for a, b in zip(quantizer.alphas, quantizer2.alphas):
                self.assertAlmostEqual(a, b, places=5)
        finally:
            db_path.unlink(missing_ok=True)


class TestSnapshotRestore(unittest.TestCase):
    def test_snapshot_restore_roundtrip(self):
        store, embedder, quantizer, indexer = build_and_populate(n=5)
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            snap_path = Path(tmp.name)
        try:
            snapshot_items(store, snap_path)
            store2 = MemoryStore()
            indexer2 = MemoryIndexer(store2, embedder, CalibratedScalarQuantizer(bits=8))
            restore_from_snapshot(snap_path, indexer2)
            self.assertEqual(set(store.memory_ids()), set(store2.memory_ids()))
        finally:
            snap_path.unlink(missing_ok=True)


class TestLoadJsonl(unittest.TestCase):
    def test_load_jsonl(self):
        rows = [
            {"memory_id": "m1", "content": "hello"},
            {"memory_id": "m2", "content": "world"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            for row in rows:
                tmp.write(json.dumps(row) + "\n")
            tmp_path = Path(tmp.name)
        try:
            loaded = load_jsonl(tmp_path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["memory_id"], "m1")
            self.assertEqual(loaded[1]["content"], "world")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_load_jsonl_skips_empty_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp.write('{"a": 1}\n\n{"b": 2}\n')
            tmp_path = Path(tmp.name)
        try:
            loaded = load_jsonl(tmp_path)
            self.assertEqual(len(loaded), 2)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
