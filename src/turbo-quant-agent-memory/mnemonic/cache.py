from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional


class EmbeddingCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def make_key(self, provider: str, model: str, text: str) -> str:
        return hashlib.sha256(f"{provider}\n{model}\n{text}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[List[float]]:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        return json.loads(path.read_text())["embedding"]

    def set(self, key: str, embedding: List[float]) -> None:
        path = self._path_for_key(key)
        path.write_text(json.dumps({"embedding": embedding}))
