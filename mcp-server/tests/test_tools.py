"""Tests for tool implementations (unit-level, no network)."""
import pytest
from solders.keypair import Keypair

from mnemonic_mcp import db, tools
from mnemonic_mcp.config import config


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    config.DATABASE_PATH = str(tmp_path / "test.db")
    config.MNEMONIC_KEYPAIR_PATH = str(tmp_path / "id.json")
    db.init_db()
    yield


@pytest.mark.asyncio
async def test_whoami():
    kp = Keypair()
    result = await tools.whoami(kp)
    assert "public_key" in result
    assert result["did_sol"].startswith("did:sol:")
    assert result["did_key"].startswith("did:key:z")
    assert result["attestation_count"] == 0


@pytest.mark.asyncio
async def test_prove_identity():
    kp = Keypair()
    result = await tools.prove_identity(kp, "test-challenge-123")
    assert result["challenge"] == "test-challenge-123"
    assert result["algorithm"] == "Ed25519"
    assert len(result["signature"]) == 128  # 64 bytes hex
    assert result["public_key"] == str(kp.pubkey())


@pytest.mark.asyncio
async def test_prove_identity_deterministic():
    kp = Keypair()
    r1 = await tools.prove_identity(kp, "same-challenge")
    r2 = await tools.prove_identity(kp, "same-challenge")
    assert r1["signature"] == r2["signature"]


@pytest.mark.asyncio
async def test_prove_identity_different_challenges():
    kp = Keypair()
    r1 = await tools.prove_identity(kp, "challenge-A")
    r2 = await tools.prove_identity(kp, "challenge-B")
    assert r1["signature"] != r2["signature"]


@pytest.mark.asyncio
async def test_recall_empty():
    kp = Keypair()
    result = await tools.recall(kp, "anything", limit=5)
    assert result["results"] == []
    assert result["total_attestations"] == 0
