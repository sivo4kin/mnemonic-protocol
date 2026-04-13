"""Solana client — SPL Memo write/read via solders + raw JSON-RPC."""
from __future__ import annotations

import json

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.message import Message
from solders.hash import Hash
import httpx

from .config import config

MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")


class SolanaClient:
    def __init__(self, rpc_url: str | None = None):
        self.rpc_url = rpc_url or config.SOLANA_RPC_URL
        self.http = httpx.AsyncClient(timeout=30)

    async def _rpc(self, method: str, params: list | None = None) -> dict:
        """Raw JSON-RPC call."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        resp = await self.http.post(self.rpc_url, json=payload)
        result = resp.json()
        if "error" in result:
            raise RuntimeError(f"Solana RPC error: {result['error']}")
        return result.get("result", {})

    async def get_latest_blockhash(self) -> str:
        result = await self._rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
        return result["value"]["blockhash"]

    async def write_memo(self, keypair: Keypair, memo_text: str) -> str:
        """Write a UTF-8 memo via SPL Memo program. Returns TX signature."""
        memo_bytes = memo_text.encode("utf-8")

        # Build memo instruction
        ix = Instruction(
            program_id=MEMO_PROGRAM_ID,
            accounts=[AccountMeta(pubkey=keypair.pubkey(), is_signer=True, is_writable=True)],
            data=memo_bytes,
        )

        blockhash_str = await self.get_latest_blockhash()
        blockhash = Hash.from_string(blockhash_str)

        msg = Message.new_with_blockhash([ix], keypair.pubkey(), blockhash)
        tx = Transaction.new_unsigned(msg)
        tx.sign([keypair], blockhash)

        # Send raw transaction
        tx_bytes = bytes(tx)
        import base64 as b64
        tx_b64 = b64.b64encode(tx_bytes).decode()
        result = await self._rpc("sendTransaction", [tx_b64, {"encoding": "base64", "skipPreflight": False}])

        sig = result if isinstance(result, str) else str(result)

        # Confirm
        await self._confirm_tx(sig)
        return sig

    async def read_memo(self, tx_sig: str) -> dict | None:
        """Read a memo from a transaction. Returns parsed memo data or None."""
        result = await self._rpc("getTransaction", [
            tx_sig,
            {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0},
        ])
        if not result:
            return None

        # Extract memo from log messages
        meta = result.get("meta", {})
        log_messages = meta.get("logMessages", [])
        for log in log_messages:
            if "Memo" in log and "len" in log:
                # Format: 'Program log: Memo (len N): "content"'
                start = log.find('"')
                end = log.rfind('"')
                if start != -1 and end > start:
                    memo_str = log[start + 1:end]
                    try:
                        return json.loads(memo_str)
                    except json.JSONDecodeError:
                        return {"raw": memo_str}

        # Fallback: parse from instructions
        tx_data = result.get("transaction", {})
        message = tx_data.get("message", {})
        instructions = message.get("instructions", [])
        for inst in instructions:
            if inst.get("programId") == str(MEMO_PROGRAM_ID):
                parsed = inst.get("parsed")
                if parsed:
                    try:
                        return json.loads(parsed)
                    except (json.JSONDecodeError, TypeError):
                        return {"raw": str(parsed)}

        return None

    async def airdrop(self, pubkey: Pubkey, lamports: int = 2_000_000_000) -> str:
        """Request airdrop (devnet/localnet only)."""
        result = await self._rpc("requestAirdrop", [str(pubkey), lamports])
        sig = result if isinstance(result, str) else str(result)
        await self._confirm_tx(sig)
        return sig

    async def get_balance(self, pubkey: Pubkey) -> int:
        """Get balance in lamports."""
        result = await self._rpc("getBalance", [str(pubkey), {"commitment": "confirmed"}])
        return result.get("value", 0)

    async def health_check(self) -> bool:
        try:
            await self._rpc("getHealth")
            return True
        except Exception:
            return False

    async def _confirm_tx(self, sig: str, max_retries: int = 30) -> None:
        """Wait for transaction confirmation."""
        import asyncio
        for _ in range(max_retries):
            result = await self._rpc("getSignatureStatuses", [[sig]])
            statuses = result.get("value", [])
            if statuses and statuses[0]:
                status = statuses[0]
                if status.get("confirmationStatus") in ("confirmed", "finalized"):
                    if status.get("err") is None:
                        return
                    raise RuntimeError(f"Transaction failed: {status['err']}")
            await asyncio.sleep(0.5)
        raise RuntimeError(f"Transaction {sig} not confirmed after {max_retries} retries")
