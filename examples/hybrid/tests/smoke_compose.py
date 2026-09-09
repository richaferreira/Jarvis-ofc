"""CI-only smoke test against the actual Compose network, without real devices or LLM calls."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiomqtt
from langchain_core.embeddings import Embeddings
from neo4j import AsyncGraphDatabase
from websockets.asyncio.client import connect

from hybrid.retrieval import ChromaRepository, Neo4jRepository
from hybrid.settings import Settings


class FixtureEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


async def main() -> None:
    settings = Settings()
    async with AsyncGraphDatabase.driver(settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())) as driver:
        async with driver.session(database=settings.neo4j_database) as session:
            for name in ("schema.cypher", "example.cypher"):
                content = "\n".join(line for line in (Path("cypher") / name).read_text().splitlines()
                                    if not line.lstrip().startswith("//"))
                for statement in content.split(";"):
                    if statement.strip():
                        result = await session.run(statement)
                        await result.consume()
        rows = await Neo4jRepository(driver, settings.neo4j_database).expand("casa01", ["circuit_c03"])
        assert rows and rows[0]["device_id"] == "tuya_qd01_c03"
        assert await Neo4jRepository(driver, settings.neo4j_database).expand("another-owner", ["circuit_c03"]) == []
    repository = await ChromaRepository.connect(settings.chroma_host, settings.chroma_port,
                                                "ci-fixture", FixtureEmbeddings())
    await repository.upsert("casa01", "smoke", "circuit_c03", "Texto de teste")
    assert (await repository.search("casa01", "sala"))[0]["entity_id"] == "circuit_c03"
    assert await repository.search("another-owner", "sala") == []
    async with connect("ws://127.0.0.1:8000/ws") as websocket:
        await websocket.send(json.dumps({"type": "auth", "token": settings.api_token.get_secret_value()}))
        assert json.loads(await websocket.recv())["type"] == "ready"
        async with aiomqtt.Client(settings.mqtt_host, username="bridge",
                                   password=settings.mqtt_password.get_secret_value()) as mqtt:
            await mqtt.publish("jarvis/casa01/devices/tuya_qd01_c03/state", json.dumps({
                "event_id": str(uuid4()), "device_id": "tuya_qd01_c03", "state": "on",
                "observed_at": datetime.now(UTC).isoformat()}), qos=1)
        async with asyncio.timeout(15):
            while True:
                event = json.loads(await websocket.recv())
                if event["type"] == "device_state":
                    assert event["device"]["state"] == "on"
                    assert event["device"]["stale"] is False
                    break
        await websocket.send(json.dumps({"type": "barge_in"}))
        async with asyncio.timeout(5):
            while json.loads(await websocket.recv())["type"] != "interrupted":
                pass
    print("PASS: Neo4j + Chroma tenant filters + MQTT -> WebSocket + barge-in control")


asyncio.run(main())
