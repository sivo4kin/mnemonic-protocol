import math
import unittest
from mnemonic.math_utils import dot, l2_norm, normalize, clip


class TestDot(unittest.TestCase):
    def test_known_vectors(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        self.assertAlmostEqual(dot(a, b), 32.0)

    def test_orthogonal(self):
        self.assertAlmostEqual(dot([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_zero_vector(self):
        self.assertAlmostEqual(dot([0.0, 0.0], [1.0, 2.0]), 0.0)


class TestL2Norm(unittest.TestCase):
    def test_unit_vector(self):
        self.assertAlmostEqual(l2_norm([1.0, 0.0, 0.0]), 1.0)

    def test_known_norm(self):
        # sqrt(1+4+9) = sqrt(14)
        self.assertAlmostEqual(l2_norm([1.0, 2.0, 3.0]), math.sqrt(14))

    def test_zero_vector(self):
        self.assertAlmostEqual(l2_norm([0.0, 0.0]), 0.0)


class TestNormalize(unittest.TestCase):
    def test_unit_vector_output(self):
        vec = [3.0, 4.0]
        normed, norm = normalize(vec)
        self.assertAlmostEqual(norm, 5.0)
        self.assertAlmostEqual(l2_norm(normed), 1.0)
        self.assertAlmostEqual(normed[0], 0.6)
        self.assertAlmostEqual(normed[1], 0.8)

    def test_zero_vector(self):
        normed, norm = normalize([0.0, 0.0, 0.0])
        self.assertEqual(norm, 0.0)
        self.assertEqual(normed, [0.0, 0.0, 0.0])

    def test_already_normalized(self):
        vec = [1.0, 0.0]
        normed, norm = normalize(vec)
        self.assertAlmostEqual(norm, 1.0)
        self.assertAlmostEqual(normed[0], 1.0)


class TestClip(unittest.TestCase):
    def test_in_range(self):
        self.assertEqual(clip(0.5, 0.0, 1.0), 0.5)

    def test_below_min(self):
        self.assertEqual(clip(-2.0, -1.0, 1.0), -1.0)

    def test_above_max(self):
        self.assertEqual(clip(3.0, -1.0, 1.0), 1.0)

    def test_at_boundaries(self):
        self.assertEqual(clip(-1.0, -1.0, 1.0), -1.0)
        self.assertEqual(clip(1.0, -1.0, 1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
