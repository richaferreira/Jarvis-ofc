"""Read-only, parameterized graph expansion combined with vector anchors."""

import hashlib
from typing import Protocol

import chromadb
from chromadb.api.models.AsyncCollection import AsyncCollection
from langchain_core.embeddings import Embeddings
from neo4j import AsyncDriver, Query

from hybrid.state import GraphHit, VectorHit


class VectorRepository(Protocol):
    async def search(self, owner: str, query: str) -> list[VectorHit]: ...


class GraphRepository(Protocol):
    async def expand(self, owner: str, entity_ids: list[str]) -> list[GraphHit]: ...


class ChromaRepository:
    def __init__(self, collection: AsyncCollection, embeddings: Embeddings) -> None:
        self.collection, self.embeddings = collection, embeddings

    @classmethod
    async def connect(cls, host: str, port: int, model: str, embeddings: Embeddings) -> "ChromaRepository":
        client = await chromadb.AsyncHttpClient(host=host, port=port)
        name = "electrical_" + hashlib.sha256(model.encode()).hexdigest()[:16]
        collection = await client.get_or_create_collection(
            name=name, embedding_function=None, metadata={"hnsw:space": "cosine"})
        return cls(collection, embeddings)

    async def search(self, owner: str, query: str) -> list[VectorHit]:
        vector = await self.embeddings.aembed_query(query)
        result = await self.collection.query(
            query_embeddings=vector, n_results=4, where={"owner": owner},
            include=["documents", "metadatas", "distances"])
        documents = (result["documents"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        distances = (result["distances"] or [[]])[0]
        hits: list[VectorHit] = []
        for index, document_id in enumerate(result["ids"][0]):
            metadata = metadatas[index] or {}
            entity = metadata.get("entity_id")
            hits.append({"document_id": document_id,
                         "entity_id": entity if isinstance(entity, str) else None,
                         "text": str(documents[index])[:1600], "distance": float(distances[index])})
        return hits

    async def upsert(self, owner: str, document_id: str, entity_id: str, text: str) -> None:
        # Chamado apenas por ingestão confiável, nunca por Cypher/texto gerado pelo LLM.
        vector = await self.embeddings.aembed_query(text)
        scoped_id = hashlib.sha256(f"{owner}\0{document_id}".encode()).hexdigest()
        await self.collection.upsert(ids=[scoped_id], documents=[text], embeddings=vector,
                                     metadatas=[{"owner": owner, "entity_id": entity_id}])


TOPOLOGY_QUERY = """
MATCH (p:Panel {owner: $owner})-[:HAS_CIRCUIT]->(c:Circuit {owner: $owner})
MATCH (c)-[:MONITORED_BY]->(d:SmartBreaker {owner: $owner})
WHERE c.id IN $ids OR d.id IN $ids
OPTIONAL MATCH (c)-[:SUPPLIES]->(r:Room {owner: $owner})
RETURN p.id AS panel, c.id AS circuit, c.name AS circuit_name,
       d.id AS device_id, d.entity_id AS entity_id,
       coalesce(r.name, '') AS room,
       coalesce(d.protection_verified, false) AS protection_verified
ORDER BY c.id, d.id
LIMIT 20
"""


class Neo4jRepository:
    def __init__(self, driver: AsyncDriver, database: str) -> None:
        self.driver, self.database = driver, database

    async def expand(self, owner: str, entity_ids: list[str]) -> list[GraphHit]:
        if not entity_ids:
            return []
        # Cada coroutine abre sua sessão; o pool do driver é compartilhado.
        async with self.driver.session(database=self.database, default_access_mode="READ") as session:
            result = await session.run(Query(TOPOLOGY_QUERY, timeout=3), owner=owner, ids=entity_ids[:8])
            hits: list[GraphHit] = []
            async for row in result:
                hits.append({"panel": str(row["panel"]), "circuit": str(row["circuit"]),
                             "circuit_name": str(row["circuit_name"]),
                             "device_id": str(row["device_id"]), "entity_id": str(row["entity_id"]),
                             "room": str(row["room"]), "protection_verified": bool(row["protection_verified"])})
            return hits
