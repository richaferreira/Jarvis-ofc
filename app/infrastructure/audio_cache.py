"""Bounded disk cache storing provider output bytes; keys never expose spoken text."""

import hashlib
import json
from pathlib import Path

from diskcache import Cache

from app.infrastructure.worker import BlockingWorker


class AudioCache:
    """SQLite-backed LRU audio cache accessed off the event loop."""

    def __init__(self, path: Path, size_mb: int, ttl: int) -> None:
        self.cache = Cache(str(path), size_limit=size_mb * 1024 * 1024,
                           eviction_policy="least-recently-used")
        self.ttl = ttl
        self.worker = BlockingWorker("audio-cache")

    @staticmethod
    def key(**parameters: str) -> str:
        """Include all synthesis parameters so voices/providers cannot collide."""
        return hashlib.sha256(json.dumps(parameters, sort_keys=True,
                                        ensure_ascii=False).encode()).hexdigest()

    async def get(self, key: str) -> bytes | None:
        return await self.worker.run(self.cache.get, key)

    def _put(self, key: str, data: bytes) -> None:
        self.cache.set(key, data, expire=self.ttl)

    async def put(self, key: str, data: bytes) -> None:
        await self.worker.run(self._put, key, data)

    async def aclose(self) -> None:
        await self.worker.run(self.cache.close)
        await self.worker.aclose()
