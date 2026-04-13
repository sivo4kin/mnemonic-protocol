"""Configuration from environment."""
from __future__ import annotations

import os
from pathlib import Path


class Config:
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "http://localhost:8899")
    ARWEAVE_URL: str = os.getenv("ARWEAVE_URL", "http://localhost:1984")
    MNEMONIC_KEYPAIR_PATH: str = os.getenv(
        "MNEMONIC_KEYPAIR_PATH",
        str(Path.home() / ".mnemonic" / "id.json"),
    )
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    DATABASE_PATH: str = os.getenv(
        "DATABASE_PATH",
        str(Path.home() / ".mnemonic" / "attestations.db"),
    )


config = Config()
