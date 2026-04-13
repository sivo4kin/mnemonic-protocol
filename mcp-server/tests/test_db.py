"""Tests for database module."""
import os
import tempfile

import pytest

from mnemonic_mcp import db
from mnemonic_mcp.config import config
from mnemonic_mcp.embed import embed_text


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    config.DATABASE_PATH = str(tmp_path / "test.db")
    db.init_db()
    yield


def test_init_creates_tables():
    conn = db.get_db()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cursor.fetchall()}
    conn.close()
    assert "attestations" in tables
    assert "attestation_embeddings" in tables


def test_save_and_count():
    emb = embed_text("test content")
    db.save_attestation(
        attestation_id="test-1",
        content="test content",
        content_hash="abc123",
        tags=["test"],
        solana_tx="sol_tx_1",
        arweave_tx="ar_tx_1",
        signer_pubkey="signer1",
        created_at="2026-04-13T00:00:00Z",
        embedding=emb,
        embedding_model="test",
    )
    assert db.count_attestations("signer1") == 1
    assert db.count_attestations("signer2") == 0


def test_search():
    for i in range(3):
        content = f"finding about topic {i}"
        emb = embed_text(content)
        db.save_attestation(
            attestation_id=f"att-{i}",
            content=content,
            content_hash=f"hash{i}",
            tags=[],
            solana_tx=f"sol{i}",
            arweave_tx=f"ar{i}",
            signer_pubkey="agent1",
            created_at="2026-04-13T00:00:00Z",
            embedding=emb,
            embedding_model="test",
        )

    query_emb = embed_text("topic 1")
    results = db.search_attestations(query_emb, "agent1", limit=2)
    assert len(results) == 2
    assert all("relevance_score" in r for r in results)
    assert results[0]["relevance_score"] >= results[1]["relevance_score"]
