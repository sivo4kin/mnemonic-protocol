from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .math_utils import clip, dot

# ---------------------------------------------------------------------------
# Attempt to import turboquant from the external submodule.
# Falls back to the legacy CalibratedScalarQuantizer if not available.
# ---------------------------------------------------------------------------
_TURBOQUANT_AVAILABLE = False
try:
    # Add external/turboquant_plus to sys.path so the submodule is importable
    _ext_path = str(Path(__file__).resolve().parent.parent.parent / "external" / "turboquant_plus")
    if _ext_path not in sys.path:
        sys.path.insert(0, _ext_path)
    import numpy as np
    from turboquant import TurboQuant, CompressedVector
    _TURBOQUANT_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Legacy quantizer (kept for backward compatibility and environments without
# numpy / turboquant)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TurboQuant adapter — same interface as CalibratedScalarQuantizer so that
# MemoryIndexer and MemoryRetriever work unchanged.
# ---------------------------------------------------------------------------

class TurboQuantAdapter:
    """Drop-in replacement for CalibratedScalarQuantizer using TurboQuant.

    Key differences from the legacy quantizer:
    - No fit() required — rotation matrix is seed-deterministic.
    - quantize_vector() returns packed bytes that encode the full CompressedVector
      (mse_indices + qjl_signs + vector_norm + residual_norm).
    - score_query_against_codes() dequantizes then dots — uses TurboQuant's
      inner-product-preserving reconstruction.
    """

    def __init__(self, bits: int = 4, dim: int = 384, seed: int = 42):
        if not _TURBOQUANT_AVAILABLE:
            raise RuntimeError(
                "TurboQuantAdapter requires numpy and turboquant. "
                "Install numpy/scipy and ensure external/turboquant_plus is present."
            )
        if bits < 2:
            raise ValueError("TurboQuant requires bits >= 2")
        self.bits = bits
        self.dim = dim
        self.seed = seed
        self._tq = TurboQuant(d=dim, bit_width=bits, seed=seed)
        self._ready = False  # becomes True after first quantize call

    def fit(self, vectors: List[List[float]]) -> None:
        """No-op for TurboQuant (seed-deterministic). Kept for interface compat."""
        # We use the first call to confirm dimensionality
        if vectors:
            actual_dim = len(vectors[0])
            if actual_dim != self.dim:
                # Reinitialize with correct dimension
                self.dim = actual_dim
                self._tq = TurboQuant(d=actual_dim, bit_width=self.bits, seed=self.seed)
        self._ready = True

    def is_fit(self) -> bool:
        return self._ready

    def quantize_vector(self, vec: List[float]) -> Tuple[bytes, float]:
        """Quantize a single vector. Returns (packed_bytes, 0.0).

        The packed bytes encode the full CompressedVector:
          [4 bytes: vector_norm f32]
          [4 bytes: residual_norm f32]
          [d bytes: mse_indices as uint8]
          [d bytes: qjl_signs as int8]
        """
        x = np.array(vec, dtype=np.float32)
        compressed = self._tq.quantize(x)
        packed = self._pack_compressed(compressed)
        return packed, 0.0  # no saturation concept in TurboQuant

    def score_query_against_codes(self, query_vec: List[float], packed_codes: bytes, dim: int) -> float:
        """Dequantize the stored vector and compute dot product with query."""
        compressed = self._unpack_compressed(packed_codes, dim)
        x_hat = self._tq.dequantize(compressed)
        q = np.array(query_vec, dtype=np.float32)
        return float(np.dot(q, x_hat))

    def average_alpha(self) -> float:
        """Return compression ratio as a diagnostic proxy for alpha."""
        return self._tq.compression_ratio(32)

    # -- Serialization: pack CompressedVector → bytes --

    def _pack_compressed(self, c: CompressedVector) -> bytes:
        """Serialize CompressedVector to a flat byte buffer."""
        buf = bytearray()
        # Two f32 norms (8 bytes)
        buf.extend(struct.pack("f", float(c.vector_norms)))
        buf.extend(struct.pack("f", float(c.residual_norms)))
        # mse_indices as uint8 (d bytes)
        buf.extend(c.mse_indices.astype(np.uint8).tobytes())
        # qjl_signs as int8 (d bytes)
        buf.extend(c.qjl_signs.astype(np.int8).tobytes())
        return bytes(buf)

    def _unpack_compressed(self, packed: bytes, dim: int) -> CompressedVector:
        """Deserialize bytes back to CompressedVector."""
        offset = 0
        vector_norm = struct.unpack_from("f", packed, offset)[0]
        offset += 4
        residual_norm = struct.unpack_from("f", packed, offset)[0]
        offset += 4
        mse_indices = np.frombuffer(packed, dtype=np.uint8, count=dim, offset=offset)
        offset += dim
        qjl_signs = np.frombuffer(packed, dtype=np.int8, count=dim, offset=offset)
        return CompressedVector(
            mse_indices=mse_indices.copy(),
            vector_norms=np.float64(vector_norm),
            qjl_signs=qjl_signs.copy(),
            residual_norms=np.float64(residual_norm),
            bit_width=self.bits,
        )

    # -- Pack/unpack compat stubs (used by some code paths) --

    def pack_codes(self, codes: List[int]) -> bytes:
        return bytes(codes)

    def unpack_codes(self, packed: bytes, dim: int) -> List[int]:
        return list(packed[:dim])
