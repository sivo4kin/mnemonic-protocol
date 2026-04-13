"""Arweave client — write/read via httpx (arlocal + production gateway)."""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

import httpx

from .config import config


class ArweaveClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.ARWEAVE_URL).rstrip("/")
        self.http = httpx.AsyncClient(timeout=60)

    async def write(self, payload: str | bytes, tags: dict[str, str] | None = None) -> str:
        """Write data to Arweave. Returns transaction ID.

        For arlocal: constructs a minimal tx with dummy crypto fields.
        For production: use Irys/Bundlr endpoint.
        """
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        tags = tags or {}
        tags.setdefault("Content-Type", "application/json")
        tags.setdefault("App-Name", "mnemonic-protocol")
        tags.setdefault("Version", "0.1.0")

        if self._is_local():
            return await self._write_arlocal(data, tags)
        else:
            return await self._write_irys(data, tags)

    async def read(self, tx_id: str) -> bytes:
        """Read data from Arweave by transaction ID."""
        url = f"{self.base_url}/{tx_id}"
        resp = await self.http.get(url)
        if resp.status_code == 404:
            raise FileNotFoundError(f"Arweave TX not found: {tx_id}")
        resp.raise_for_status()
        return resp.content

    async def mine(self) -> None:
        """Mine a block on arlocal (no-op on production)."""
        if self._is_local():
            await self.http.get(f"{self.base_url}/mine")

    async def health_check(self) -> bool:
        try:
            resp = await self.http.get(f"{self.base_url}/info")
            return resp.status_code == 200
        except Exception:
            return False

    def _is_local(self) -> bool:
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    async def _write_arlocal(self, data: bytes, tags: dict[str, str]) -> str:
        """Write to arlocal with minimal unsigned tx."""
        import base64 as b64
        import secrets

        def b64url(b: bytes) -> str:
            return b64.urlsafe_b64encode(b).rstrip(b"=").decode()

        sig_bytes = secrets.token_bytes(512)
        id_hash = hashlib.sha256(sig_bytes).digest()
        owner_bytes = secrets.token_bytes(256)
        data_root = hashlib.sha256(data).digest()

        encoded_tags = [
            {"name": b64url(k.encode()), "value": b64url(v.encode())}
            for k, v in tags.items()
        ]

        tx = {
            "format": 2,
            "id": b64url(id_hash),
            "last_tx": "",
            "owner": b64url(owner_bytes),
            "tags": encoded_tags,
            "target": "",
            "quantity": "0",
            "data_size": str(len(data)),
            "data": b64url(data),
            "data_root": b64url(data_root),
            "reward": "0",
            "signature": b64url(sig_bytes),
        }

        resp = await self.http.post(f"{self.base_url}/tx", json=tx)
        if resp.status_code >= 400:
            raise RuntimeError(f"Arweave write failed: {resp.status_code} {resp.text}")
        return tx["id"]

    async def _write_irys(self, data: bytes, tags: dict[str, str]) -> str:
        """Write to production Arweave via Irys bundler."""
        resp = await self.http.post(
            "https://uploader.irys.xyz/upload",
            content=data,
            headers={"Content-Type": "application/octet-stream", "x-network": "arweave"},
        )
        if not resp.is_success:
            raise RuntimeError(f"Irys upload failed: {resp.status_code} {resp.text}")
        result = resp.json()
        return result["id"]
