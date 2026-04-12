from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "mnemonic_v1.db")

    # Chat providers
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # Embedding
    EMBED_PROVIDER: str = os.getenv("EMBED_PROVIDER", "fastembed")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # Available providers for UI
    def available_providers(self) -> list[dict]:
        providers = []
        if self.ANTHROPIC_API_KEY:
            providers.append({"provider": "anthropic", "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]})
        if self.OPENAI_API_KEY:
            providers.append({"provider": "openai", "models": ["gpt-4o", "gpt-4o-mini"]})
        if self.QWEN_API_KEY:
            providers.append({"provider": "qwen", "models": ["qwen-plus", "qwen-turbo"]})
        return providers


settings = Settings()
