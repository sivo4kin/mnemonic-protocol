import tempfile
import unittest
from pathlib import Path
from mnemonic.cache import EmbeddingCache


class TestEmbeddingCache(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = EmbeddingCache(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_set_then_get_returns_same_values(self):
        key = "abc123"
        embedding = [0.1, 0.2, 0.3, 0.4]
        self.cache.set(key, embedding)
        result = self.cache.get(key)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), len(embedding))
        for a, b in zip(result, embedding):
            self.assertAlmostEqual(a, b)

    def test_get_missing_key_returns_none(self):
        result = self.cache.get("nonexistent_key")
        self.assertIsNone(result)

    def test_make_key_deterministic(self):
        k1 = self.cache.make_key("openai", "text-embedding-3-small", "hello world")
        k2 = self.cache.make_key("openai", "text-embedding-3-small", "hello world")
        self.assertEqual(k1, k2)

    def test_make_key_different_inputs(self):
        k1 = self.cache.make_key("openai", "text-embedding-3-small", "hello")
        k2 = self.cache.make_key("openai", "text-embedding-3-small", "world")
        self.assertNotEqual(k1, k2)

    def test_cache_dir_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "deep" / "nested"
            cache = EmbeddingCache(subdir)
            self.assertTrue(subdir.exists())


if __name__ == "__main__":
    unittest.main()
