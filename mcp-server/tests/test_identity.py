"""Tests for identity module."""
import json
import tempfile
from pathlib import Path

from solders.keypair import Keypair

from mnemonic_mcp.identity import (
    pubkey_base58, did_sol, did_key, sign_message, verify_signature,
)


def test_pubkey_base58():
    kp = Keypair()
    pk = pubkey_base58(kp)
    assert len(pk) > 30  # base58 encoded Ed25519 pubkey
    assert pk == str(kp.pubkey())


def test_did_sol():
    kp = Keypair()
    d = did_sol(kp)
    assert d.startswith("did:sol:")
    assert str(kp.pubkey()) in d


def test_did_key():
    kp = Keypair()
    d = did_key(kp)
    assert d.startswith("did:key:z")
    assert len(d) > 20


def test_did_key_deterministic():
    kp = Keypair()
    assert did_key(kp) == did_key(kp)


def test_sign_and_verify():
    kp = Keypair()
    msg = b"hello mnemonic"
    sig = sign_message(kp, msg)
    assert len(sig) == 64  # Ed25519 signature
    assert verify_signature(kp.pubkey(), msg, sig)


def test_sign_different_messages_differ():
    kp = Keypair()
    s1 = sign_message(kp, b"message A")
    s2 = sign_message(kp, b"message B")
    assert s1 != s2


def test_verify_wrong_message_fails():
    kp = Keypair()
    sig = sign_message(kp, b"correct message")
    assert not verify_signature(kp.pubkey(), b"wrong message", sig)
