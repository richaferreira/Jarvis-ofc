"""Explicit example ingestion; never run automatically against existing installations."""

import asyncio
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from neo4j import AsyncGraphDatabase

from hybrid.retrieval import ChromaRepository
from hybrid.settings import Settings


async def seed() -> None:
    settings = Settings()
    if settings.owner != "casa01":
        raise ValueError("Adapte os exemplos Cypher ao OWNER antes da ingestão.")
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
    vectors = await ChromaRepository.connect(settings.chroma_host, settings.chroma_port,
        settings.embedding_model, OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_url))
    await vectors.upsert(settings.owner, "c03-descricao", "circuit_c03",
                         "Exemplo cadastral: o circuito circuit_c03 alimenta a iluminação da sala e "
                         "é monitorado pelo dispositivo tuya_qd01_c03 instalado no quadro qd01. "
                         "A função de proteção elétrica não foi verificada.")


if __name__ == "__main__":
    asyncio.run(seed())
