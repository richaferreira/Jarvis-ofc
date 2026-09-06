import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app.core.agent import JarvisAgent
from app.exceptions import BusyError
from app.memory.memory import DisabledMemory


class Model:
    def __init__(self, replies):
        self.replies, self.messages = list(replies), []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return self.replies.pop(0)


class Registry:
    def __init__(self):
        self.calls = 0

    def build(self, owner, session):
        async def clock() -> dict:
            """Return fake time."""
            self.calls += 1
            return {"time": "12:00"}

        return [StructuredTool.from_function(coroutine=clock, name="clock")]


async def test_real_graph_executes_tool_and_isolates_session_history(settings):
    model = Model([AIMessage(content="", tool_calls=[{"name": "clock", "args": {}, "id": "t1"}]),
                   AIMessage(content="São 12 horas."), AIMessage(content="Olá.")])
    registry = Registry()
    agent = JarvisAgent(settings, model, DisabledMemory(), registry)
    response = await agent.chat("owner", "one", "Que horas são?")
    assert response.text == "São 12 horas."
    assert registry.calls == 1
    await agent.chat("other", "one", "Olá")
    assert all("Que horas" not in str(m.content) for m in model.messages[-1])
    assert len(agent.buffer.messages("owner", "one")) == 2


async def test_graph_stops_repeated_calls_at_budget(settings):
    settings.max_tool_rounds = 1
    repeated = AIMessage(content="", tool_calls=[{"name": "clock", "args": {}, "id": "t1"}])
    model, registry = Model([repeated, repeated]), Registry()
    response = await JarvisAgent(settings, model, DisabledMemory(), registry).chat("u", "s", "Teste")
    assert "limite" in response.text
    assert registry.calls == 1


async def test_unknown_tool_cannot_execute_and_retrieval_can_fail(settings):
    class BrokenMemory(DisabledMemory):
        async def recall(self, owner, query):
            raise RuntimeError("offline")

    model = Model([AIMessage(content="", tool_calls=[{"name": "confirm_home_action", "args": {}, "id": "t"}]),
                   AIMessage(content="Não executei.")])
    registry = Registry()
    result = await JarvisAgent(settings, model, BrokenMemory(), registry).chat("u", "s", "Faça")
    assert result.warnings
    assert registry.calls == 0
    assert "não permitida" in str(model.messages[-1][-1].content)


async def test_admission_rejects_overlapping_turns(settings):
    started, release = asyncio.Event(), asyncio.Event()

    class WaitingModel(Model):
        async def ainvoke(self, messages):
            started.set()
            await release.wait()
            return AIMessage(content="Ok")

    agent = JarvisAgent(settings, WaitingModel([]), DisabledMemory(), Registry())
    first = asyncio.create_task(agent.chat("u", "s", "A"))
    await started.wait()
    with pytest.raises(BusyError):
        await agent.chat("u", "s", "B")
    release.set()
    await first
