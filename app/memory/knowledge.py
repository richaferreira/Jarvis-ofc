"""Atomic JSON knowledge, independent of vector model availability."""
import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions import JarvisError


class KnowledgeStore:
    _locks: dict[str, asyncio.Lock] = {}
    def __init__(self, directory: Path) -> None:
        self.path = directory / 'knowledge.json'
        self.lock = self._locks.setdefault(str(self.path.resolve()), asyncio.Lock())

    def _read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
                raise ValueError()
            return data
        except (ValueError, OSError) as exc:
            raise JarvisError('Memória JSON inválida ou ilegível. O arquivo foi preservado.') from exc

    def _write(self, entries: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(entries, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def list(self, owner: str) -> list[dict[str, str]]:
        async with self.lock:
            return [x for x in await asyncio.to_thread(self._read) if x.get('owner') == owner]

    async def save(self, owner: str, category: str, text: str) -> str:
        async with self.lock:
            data = await asyncio.to_thread(self._read)
            key = uuid.uuid4().hex
            data.append(dict(id=key, owner=owner, category=category, text=text,
                             created=datetime.now(timezone.utc).isoformat()))
            await asyncio.to_thread(self._write, data[-500:])
            return key

    async def delete(self, owner: str, key: str) -> None:
        async with self.lock:
            data = await asyncio.to_thread(self._read)
            await asyncio.to_thread(self._write, [x for x in data if not (x.get('owner') == owner and x.get('id') == key)])

    async def recall(self, owner: str, query: str) -> list[str]:
        words = {w.lower() for w in query.split() if len(w) > 2}
        entries = await self.list(owner)
        ranked = sorted(entries, key=lambda x: sum(w in x.get('text', '').lower() for w in words)
                        + (1 if x.get('category') == 'preference' else 0), reverse=True)
        return [x['text'][:2000] for x in ranked[:4] if x.get('text')]
