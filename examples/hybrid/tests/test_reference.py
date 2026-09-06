import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from hybrid.graph import HybridAgent, route_intent
from hybrid.mqtt import DeviceEvent, StateHub
from hybrid.server import SocketSession
from hybrid.settings import Settings


def test_intent():
    assert route_intent("Olá!") == "conversation"
    assert route_intent("Qual disjuntor está ligado agora?") == "hybrid"
    assert route_intent("Qual circuito alimenta a sala?") == "topology"


def test_mqtt_dedup_order_and_stale():
    hub = StateHub(["d1"], ttl=30)
    hub.connected = True
    now = datetime.now(UTC)
    event = DeviceEvent(event_id=uuid4(), device_id="d1", state="on", observed_at=now)
    assert hub.accept(event, retained=False)
    assert not hub.accept(event, retained=False)
    assert not hub.accept(event.model_copy(update={"event_id": uuid4(), "observed_at": now - timedelta(seconds=1)}), False)
    assert hub.snapshot()[0]["stale"] is False
    hub.connected = False
    assert hub.snapshot()[0]["stale"] is True
    assert not hub.accept(event.model_copy(update={"device_id": "other"}), False)


async def test_subscribers_receive_independently_and_retained_age_is_preserved():
    hub = StateHub(["d1"], 10)
    hub.connected = True
    async with hub.subscribe() as a, hub.subscribe() as b:
        old = DeviceEvent(event_id=uuid4(), device_id="d1", state="off",
                          observed_at=datetime.now(UTC) - timedelta(seconds=20))
        hub.accept(old, True)
        assert (await a.get())["stale"] is True
        assert (await b.get())["retained"] is True


class Vectors:
    async def search(self, owner, query):
        return [{"document_id": "doc1", "entity_id": "circuit_c03", "text": "Sala", "distance": 0.1}]


class Topology:
    def __init__(self):
        self.calls = []

    async def expand(self, owner, entity_ids):
        self.calls.append((owner, entity_ids))
        return [{"panel": "qd01", "circuit": "circuit_c03", "circuit_name": "Sala",
                 "device_id": "tuya_qd01_c03", "entity_id": "switch.sala", "room": "Sala",
                 "protection_verified": False}]


async def test_graph_anchors_and_streams_actual_langgraph():
    topology = Topology()
    agent = HybridAgent(FakeListChatModel(responses=["Resposta"]), Vectors(), topology,
                        StateHub(["tuya_qd01_c03"], 30))
    events = [event async for event in agent.stream("owner", "Qual circuito alimenta a sala?")]
    assert topology.calls == [("owner", ["circuit_c03"])]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Resposta"
    assert any(e["type"] == "context" for e in events)


async def test_websocket_interruption_cancels_generation():
    class Socket:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    class Agent:
        async def stream(self, owner, text):
            yield {"type": "token", "text": "first"}
            await asyncio.sleep(60)

    settings = Settings(_env_file=None, api_token="x" * 32, neo4j_password="test-password",
                        mqtt_password="test-password")
    socket = Socket()
    session = SocketSession(socket, Agent(), StateHub([], 30), settings)
    session.generation = "old"
    task = asyncio.create_task(session.respond("Hi", "old"))
    session.answer_task = task
    await asyncio.sleep(0.01)
    await session.stop_answer()
    assert task.cancelled()
    before = len(socket.events)
    await session.send({"type": "token", "text": "late"}, "old")
    assert len(socket.events) == before
