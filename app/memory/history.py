"""Local bounded transcript persistence; no credentials or action tokens stored."""
import asyncio
import sqlite3
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / 'conversations.sqlite3'

    def _query(self, operation: str, owner: str, session: str = '', human: str = '', answer: str = '') -> list[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5) as db:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, owner TEXT, session TEXT, human TEXT, answer TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute('CREATE INDEX IF NOT EXISTS turns_session ON turns(owner, session, id)')
            if operation == 'append':
                db.execute('INSERT INTO turns(owner,session,human,answer) VALUES(?,?,?,?)', (owner, session, human, answer))
                db.execute('DELETE FROM turns WHERE owner=? AND session=? AND id NOT IN (SELECT id FROM turns WHERE owner=? AND session=? ORDER BY id DESC LIMIT 30)', (owner,session,owner,session))
                db.execute('DELETE FROM turns WHERE owner=? AND session NOT IN (SELECT session FROM turns WHERE owner=? GROUP BY session ORDER BY MAX(id) DESC LIMIT 64)', (owner,owner))
            elif operation == 'clear':
                db.execute('DELETE FROM turns WHERE owner=? AND session=?', (owner,session))
            elif operation == 'sessions':
                return [dict(row) for row in db.execute('SELECT session, substr(MIN(human),1,80) AS title, MAX(created) AS updated FROM turns WHERE owner=? GROUP BY session ORDER BY MAX(id) DESC LIMIT 64', (owner,))]
            elif operation == 'read':
                return [dict(row) for row in db.execute('SELECT human,answer,created FROM turns WHERE owner=? AND session=? ORDER BY id', (owner,session))]
        return []

    async def query(self, operation: str, owner: str, session: str = '', human: str = '', answer: str = '') -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._query, operation, owner, session, human, answer)
