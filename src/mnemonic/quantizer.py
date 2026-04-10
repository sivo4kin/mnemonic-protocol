from __future__ import annotations

from typing import List, Optional, Tuple

from .math_utils import clip


class CalibratedScalarQuantizer:
    def __init__(self, bits: int = 8, default_alpha: float = 0.25):
        if bits not in (4, 8):
            raise ValueError("Only 4-bit and 8-bit modes are supported")
        self.bits = bits
        self.levels = 2 ** bits
        self.max_int = self.levels - 1
        self.default_alpha = default_alpha
        self.alphas: Optional[List[float]] = None
        self.steps: Optional[List[float]] = None

    def fit(self, vectors: List[List[float]]) -> None:
        if not vectors:
            raise ValueError("Need at least one vector to calibrate quantizer")
        dim = len(vectors[0])
        alphas = []
        steps = []
        for j in range(dim):
            values = [abs(v[j]) for v in vectors]
            ordered = sorted(values)
            idx = min(len(ordered) - 1, max(0, int(0.98 * (len(ordered) - 1))))
            alpha = max(ordered[idx], self.default_alpha / 8.0)
            alpha = min(alpha, 1.0)
            alphas.append(alpha)
            steps.append((2.0 * alpha) / self.max_int)
        self.alphas = alphas
        self.steps = steps

    def is_fit(self) -> bool:
        return self.alphas is not None and self.steps is not None

    def quantize_vector(self, vec: List[float]) -> Tuple[bytes, float]:
        if not self.is_fit():
            raise RuntimeError("Quantizer must be fit before use")
        codes: List[int] = []
        saturated = 0
        assert self.alphas is not None and self.steps is not None
        for x, alpha, step in zip(vec, self.alphas, self.steps):
            x_clipped = clip(x, -alpha, alpha)
            if x_clipped != x:
                saturated += 1
            q = round((x_clipped + alpha) / step)
            q = max(0, min(self.max_int, int(q)))
            codes.append(q)
        return self.pack_codes(codes), saturated / max(1, len(vec))

    def score_query_against_codes(self, query_vec: List[float], packed_codes: bytes, dim: int) -> float:
        if not self.is_fit():
            raise RuntimeError("Quantizer must be fit before use")
        assert self.alphas is not None and self.steps is not None
        codes = self.unpack_codes(packed_codes, dim)
        # Precompute reconstructed values and use fast dot product
        return sum(qx * (-a + q * s) for qx, q, a, s in zip(query_vec, codes, self.alphas, self.steps))

    def average_alpha(self) -> float:
        if not self.alphas:
            return self.default_alpha
        return sum(self.alphas) / len(self.alphas)

    def pack_codes(self, codes: List[int]) -> bytes:
        if self.bits == 8:
            return bytes(codes)
        packed = bytearray()
        for i in range(0, len(codes), 2):
            a = codes[i]
            b = codes[i + 1] if i + 1 < len(codes) else 0
            packed.append((a << 4) | b)
        return bytes(packed)

    def unpack_codes(self, packed: bytes, dim: int) -> List[int]:
        if self.bits == 8:
            return list(packed[:dim])
        out: List[int] = []
        for byte in packed:
            out.append((byte >> 4) & 0x0F)
            out.append(byte & 0x0F)
            if len(out) >= dim:
                break
        return out[:dim]
