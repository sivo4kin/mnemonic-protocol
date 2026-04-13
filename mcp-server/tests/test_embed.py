"""Tests for embedding module."""
from mnemonic_mcp.embed import embed_text, cosine_similarity, get_dim


def test_embed_deterministic():
    v1 = embed_text("hello world")
    v2 = embed_text("hello world")
    assert v1 == v2


def test_embed_different_texts_differ():
    v1 = embed_text("hello world")
    v2 = embed_text("goodbye world")
    assert v1 != v2


def test_embed_dimension():
    v = embed_text("test")
    assert len(v) == get_dim()
    assert get_dim() == 384


def test_cosine_self_similarity():
    v = embed_text("test similarity")
    sim = cosine_similarity(v, v)
    assert abs(sim - 1.0) < 1e-5


def test_cosine_different_texts():
    v1 = embed_text("quantum physics research")
    v2 = embed_text("chocolate cake recipe")
    sim = cosine_similarity(v1, v2)
    assert sim < 0.95  # should be meaningfully different
