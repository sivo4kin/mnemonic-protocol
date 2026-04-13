"""Mnemonic MCP Server — stdio transport with 5 identity tools."""
from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import db
from .identity import load_or_create_keypair
from . import tools

logger = logging.getLogger("mnemonic-mcp")

# Tool definitions matching the spec from the Agent Identity PDF
TOOLS = [
    Tool(
        name="mnemonic_whoami",
        description=(
            "Returns this agent's cryptographic identity: Solana public key, "
            "did:sol identifier, did:key identifier, and memory attestation count."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="mnemonic_sign_memory",
        description=(
            "Creates a verifiable memory attestation: embeds content, computes SHA-256, "
            "stores on Arweave, anchors hash on Solana via SPL Memo. Returns attestation proof."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to attest (text, code, or structured data)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional semantic tags",
                },
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="mnemonic_verify",
        description=(
            "Verifies a memory attestation by recomputing the hash and comparing "
            "against the on-chain record. Proves who signed what and when."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "solana_tx": {
                    "type": "string",
                    "description": "Solana transaction signature to verify",
                },
                "arweave_tx": {
                    "type": "string",
                    "description": "Arweave transaction ID (alternative to solana_tx)",
                },
            },
        },
    ),
    Tool(
        name="mnemonic_prove_identity",
        description=(
            "Signs an arbitrary challenge with the agent's private key, proving "
            "control of the identity without an on-chain transaction."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "challenge": {
                    "type": "string",
                    "description": "Challenge string to sign (nonce, timestamp, or counterparty-provided)",
                },
            },
            "required": ["challenge"],
        },
    ),
    Tool(
        name="mnemonic_recall",
        description=(
            "Searches the agent's attested memory history using semantic similarity. "
            "Returns matching records with full attestation proofs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    ),
]


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("mnemonic")

    # Initialize DB and keypair
    db.init_db()
    keypair = load_or_create_keypair()

    logger.info(f"Mnemonic identity: {keypair.pubkey()}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "mnemonic_whoami":
                result = await tools.whoami(keypair)
            elif name == "mnemonic_sign_memory":
                result = await tools.sign_memory(
                    keypair,
                    content=arguments["content"],
                    tags=arguments.get("tags"),
                )
            elif name == "mnemonic_verify":
                result = await tools.verify(
                    keypair,
                    solana_tx=arguments.get("solana_tx"),
                    arweave_tx=arguments.get("arweave_tx"),
                )
            elif name == "mnemonic_prove_identity":
                result = await tools.prove_identity(
                    keypair,
                    challenge=arguments["challenge"],
                )
            elif name == "mnemonic_recall":
                result = await tools.recall(
                    keypair,
                    query=arguments["query"],
                    limit=arguments.get("limit", 5),
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}),
            )]

    return server


async def main() -> None:
    """Run the MCP server over stdio."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
