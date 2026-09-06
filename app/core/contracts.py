"""Protocols separating orchestration from model and memory implementations."""

from typing import Any, Protocol

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


class ChatModel(Protocol):
    """Minimal interface implemented by supported LangChain chat models."""

    def bind_tools(self, tools: list[BaseTool]) -> Any: ...
    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> Any: ...


class MemoryBackend(Protocol):
    """Long-term storage contract; identity is supplied by trusted runtime code."""

    async def recall(self, owner: str, query: str) -> list[str]: ...
    async def remember(self, owner: str, text: str) -> str: ...
    async def forget(self, owner: str) -> None: ...
    async def aclose(self) -> None: ...
