import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessageChunk

from app.api.launcher import reserve_port
from app.core.agent import JarvisAgent
from app.memory.history import HistoryStore
from app.memory.memory import DisabledMemory


class StreamModel:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield AIMessageChunk(content='Olá ')
        await asyncio.sleep(0)
        yield AIMessageChunk(content='Richardson')


def registry():
    return SimpleNamespace(build=lambda *_: [], home=SimpleNamespace(clear_session=AsyncMock()))


async def test_stream_emits_real_chunks_and_persists_complete_pair(settings):
    agent = JarvisAgent(settings, StreamModel(), DisabledMemory(), registry())
    events = []
    async def emit(event):
        events.append(event)
    response = await agent.chat('owner', 'session', 'Oi', emit=emit)
    assert response.text == 'Olá Richardson'
    assert [e['text'] for e in events if e['type'] == 'token'] == ['Olá ', 'Richardson']
    restarted = HistoryStore(settings.data_dir)
    assert (await restarted.query('read', 'owner', 'session'))[0]['answer'] == response.text
    assert await restarted.query('read', 'other', 'session') == []
    await agent.clear('owner', 'session')
    assert await restarted.query('read', 'owner', 'session') == []


async def test_cancel_stream_revokes_pending_and_releases_gate(settings):
    entered = asyncio.Event()
    class Waiting(StreamModel):
        async def astream(self, messages):
            yield AIMessageChunk(content='Parcial')
            entered.set()
            await asyncio.Event().wait()
    tools = registry()
    agent = JarvisAgent(settings, Waiting(), DisabledMemory(), tools)
    async def emit(_):
        pass
    task = asyncio.create_task(agent.chat('owner', 's', 'Oi', emit=emit))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    tools.home.clear_session.assert_awaited_once_with('owner','s')
    assert not agent._gate.locked()
    assert await agent.history.query('read', 'owner', 's') == []


def test_launcher_reserves_next_port_without_stopping_existing_process():
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        with reserve_port('127.0.0.1', occupied.getsockname()[1]) as reserved:
            assert reserved.getsockname()[1] != occupied.getsockname()[1]


async def test_slow_vector_recall_does_not_block_json_or_stream(settings):
    settings.memory_recall_timeout = 0.1
    cancelled = asyncio.Event()
    class SlowMemory:
        async def recall(self, *_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    agent = JarvisAgent(settings, StreamModel(), SlowMemory(), registry())
    await agent.knowledge.save('owner', 'preference', 'Responda em português')
    events = []
    async def emit(event):
        events.append(event)
    response = await asyncio.wait_for(agent.chat('owner', 's', 'Oi', emit=emit), 2)
    assert cancelled.is_set()
    assert response.text == 'Olá Richardson'
    assert any('vetorial' in warning for warning in response.warnings)
    assert [item['type'] for item in events][-1] == 'answer'


async def test_final_answer_is_emitted_before_history_write(settings):
    agent = JarvisAgent(settings, StreamModel(), DisabledMemory(), registry())
    answer_ready = asyncio.Event()
    original = agent.history.query
    async def query(operation, *args):
        if operation == 'append':
            assert answer_ready.is_set()
        return await original(operation, *args)
    agent.history.query = query
    async def emit(event):
        if event['type'] == 'answer':
            answer_ready.set()
    await agent.chat('owner', 's', 'Oi', emit=emit)
    assert answer_ready.is_set()
