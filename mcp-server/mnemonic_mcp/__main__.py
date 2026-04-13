"""Entry point: python -m mnemonic_mcp"""
import asyncio
from .server import main

asyncio.run(main())
