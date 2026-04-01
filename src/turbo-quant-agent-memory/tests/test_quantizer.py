import random
import unittest
from mnemonic.quantizer import CalibratedScalarQuantizer


def make_vectors(n: int, dim: int, seed: int = 42) -> list:
    rng = random.Random(seed)
    return [[rng.gauss(0, 0.3) for _ in range(dim)] for _ in range(n)]


class TestCalibratedScalarQuantizer(unittest.TestCase):
    def test_raises_before_fit_quantize(self):
        q = CalibratedScalarQuantizer(bits=8)
        with self.assertRaises(RuntimeError):
            q.quantize_vector([0.1] * 4)

    def test_raises_before_fit_score(self):
        q = CalibratedScalarQuantizer(bits=8)
        with self.assertRaises(RuntimeError):
            q.score_query_against_codes([0.1] * 4, b"\x00" * 4, 4)

    def test_is_fit_after_fit(self):
        q = CalibratedScalarQuantizer(bits=8)
        vecs = make_vectors(10, 4)
        self.assertFalse(q.is_fit())
        q.fit(vecs)
        self.assertTrue(q.is_fit())

    def test_quantize_returns_bytes(self):
        q = CalibratedScalarQuantizer(bits=8)
        vecs = make_vectors(10, 4)
        q.fit(vecs)
        packed, sat = q.quantize_vector(vecs[0])
        self.assertIsInstance(packed, bytes)
        self.assertGreaterEqual(sat, 0.0)
        self.assertLessEqual(sat, 1.0)

    def test_pack_unpack_roundtrip_8bit(self):
        q = CalibratedScalarQuantizer(bits=8)
        vecs = make_vectors(10, 8)
        q.fit(vecs)
        codes = [10, 200, 0, 255, 128, 64, 32, 16]
        packed = q.pack_codes(codes)
        unpacked = q.unpack_codes(packed, 8)
        self.assertEqual(unpacked, codes)

    def test_pack_unpack_roundtrip_4bit(self):
        q = CalibratedScalarQuantizer(bits=4)
        vecs = make_vectors(10, 8)
        q.fit(vecs)
        codes = [0, 15, 7, 3, 12, 1, 8, 4]
        packed = q.pack_codes(codes)
        unpacked = q.unpack_codes(packed, 8)
        self.assertEqual(unpacked, codes)

    def test_score_self_vs_random(self):
        q = CalibratedScalarQuantizer(bits=8)
        vecs = make_vectors(20, 16)
        q.fit(vecs)
        from mnemonic.math_utils import normalize
        query = vecs[0]
        query_normed, _ = normalize(query)
        # Re-quantize normalized vectors
        vecs_normed = [normalize(v)[0] for v in vecs]
        q.fit(vecs_normed)
        packed_self, _ = q.quantize_vector(query_normed)
        # Random vector
        rng = random.Random(999)
        random_vec = [rng.gauss(0, 1) for _ in range(16)]
        random_normed, _ = normalize(random_vec)
        packed_random, _ = q.quantize_vector(random_normed)
        score_self = q.score_query_against_codes(query_normed, packed_self, 16)
        score_random = q.score_query_against_codes(query_normed, packed_random, 16)
        self.assertGreater(score_self, score_random)

    def test_fit_empty_raises(self):
        q = CalibratedScalarQuantizer(bits=8)
        with self.assertRaises(ValueError):
            q.fit([])

    def test_invalid_bits_raises(self):
        with self.assertRaises(ValueError):
            CalibratedScalarQuantizer(bits=16)


if __name__ == "__main__":
    unittest.main()
