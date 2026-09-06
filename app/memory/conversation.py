"""Bounded, expiring conversation buffer storing only completed user/assistant pairs."""

import time
from collections import OrderedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class ConversationBuffer:
    """In-process LRU history; access is serialized by the agent admission gate."""

    def __init__(self, max_sessions: int, turns: int, chars: int, ttl: int) -> None:
        self.max_sessions, self.turns, self.chars, self.ttl = max_sessions, turns, chars, ttl
        self._items: OrderedDict[tuple[str, str], tuple[float, list[tuple[str, str]]]] = OrderedDict()

    def _expire(self) -> None:
        now = time.monotonic()
        for key, (updated, _) in list(self._items.items()):
            if now - updated >= self.ttl:
                del self._items[key]

    def messages(self, owner: str, session: str) -> list[BaseMessage]:
        """Read completed pairs; never retain orphan tool messages."""
        self._expire()
        key = (owner, session)
        if key not in self._items:
            return []
        self._items.move_to_end(key)
        _, turns = self._items[key]
        return [message for human, ai in turns for message in
                (HumanMessage(content=human), AIMessage(content=ai))]

    def append(self, owner: str, session: str, human: str, ai: str) -> None:
        """Evict complete turns to satisfy both count and character budgets."""
        self._expire()
        key = (owner, session)
        turns = list(self._items.get(key, (0, []))[1])
        turns.append((human, ai))
        while turns and (len(turns) > self.turns or sum(len(h) + len(a) for h, a in turns) > self.chars):
            turns.pop(0)
        self._items[key] = (time.monotonic(), turns)
        self._items.move_to_end(key)
        while len(self._items) > self.max_sessions:
            self._items.popitem(last=False)

    def clear(self, owner: str, session: str) -> None:
        """Delete only the selected conversation."""
        self._items.pop((owner, session), None)
