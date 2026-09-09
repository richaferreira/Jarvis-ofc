"""Revocable browser sessions: hashed server storage and a scoped HttpOnly cookie."""
import asyncio
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path


class BrowserSessions:
    def __init__(self, directory: Path, api_token: str) -> None:
        self.path = directory / 'browser_sessions.sqlite3'
        self.key_id = hashlib.sha256(api_token.encode()).hexdigest()

    def _operation(self, operation: str, token: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = time.time()
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, key_id TEXT, expires REAL)')
            db.execute('DELETE FROM sessions WHERE expires < ? OR key_id != ?', (now, self.key_id))
            if operation == 'create':
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest, self.key_id, now+30*86400))
                db.execute('DELETE FROM sessions WHERE hash NOT IN (SELECT hash FROM sessions ORDER BY expires DESC LIMIT 32)')
            elif operation == 'delete':
                db.execute('DELETE FROM sessions WHERE hash=?', (digest,))
            return db.execute('SELECT 1 FROM sessions WHERE hash=? AND key_id=? AND expires>?', (digest,self.key_id,now)).fetchone() is not None

    async def create(self) -> str:
        token = secrets.token_urlsafe(32)
        await asyncio.to_thread(self._operation, 'create', token)
        return token

    async def valid(self, token: str) -> bool:
        if not token or len(token) > 256:
            return False
        return await asyncio.to_thread(self._operation, 'read', token)

    async def revoke(self, token: str) -> None:
        await asyncio.to_thread(self._operation, 'delete', token)
