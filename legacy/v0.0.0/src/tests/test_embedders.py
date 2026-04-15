import tempfile
import unittest
from pathlib import Path
from mnemonic.embedders import MockEmbeddingProvider, build_embedder


class TestMockEmbeddingProvider(unittest.TestCase):
    def setUp(self):
        self.embedder = MockEmbeddingProvider(dim=64)

    def test_embed_text_returns_floats(self):
        result = self.embedder.embed_text("hello world")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 64)
        for v in result:
            self.assertIsInstance(v, float)

    def test_deterministic_same_text(self):
        text = "agent memory quantization"
        r1 = self.embedder.embed_text(text)
        r2 = self.embedder.embed_text(text)
        self.assertEqual(r1, r2)

    def test_different_texts_differ(self):
        r1 = self.embedder.embed_text("quantization compression")
        r2 = self.embedder.embed_text("blockchain wallet transaction")
        self.assertNotEqual(r1, r2)

    def test_different_salt_different_embedding(self):
        e1 = MockEmbeddingProvider(dim=64, salt="salt_a")
        e2 = MockEmbeddingProvider(dim=64, salt="salt_b")
        text = "the same text"
        self.assertNotEqual(e1.embed_text(text), e2.embed_text(text))

    def test_provider_name(self):
        self.assertEqual(self.embedder.provider_name(), "mock")

    def test_dim_respected(self):
        for dim in [32, 128, 256]:
            e = MockEmbeddingProvider(dim=dim)
            result = e.embed_text("test")
            self.assertEqual(len(result), dim)


class TestBuildEmbedder(unittest.TestCase):
    def test_build_mock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = build_embedder("mock", cache_dir=Path(tmpdir), dim=64)
            self.assertIsInstance(embedder, MockEmbeddingProvider)
            self.assertEqual(embedder.dim, 64)

    def test_build_unknown_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_embedder("unknown", cache_dir=Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
