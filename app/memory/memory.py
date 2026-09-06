"""Persistent user preferences with explicit writes and identity-filtered RAG."""

import hashlib

from app.config import Settings
from app.exceptions import ServiceUnavailable
from app.infrastructure.worker import BlockingWorker
from app.memory.embeddings import LocalEmbeddings
from app.memory.vector_store import VectorStore


class MemoryService:
    """Serialize local embeddings and Chroma access without blocking asyncio."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker = BlockingWorker("memory")
        self._ready = False

    def _initialize(self) -> None:
        self.embeddings = LocalEmbeddings(self.settings.embedding_model,
                                          self.settings.data_dir / "models")
        self.store = VectorStore(self.settings.data_dir / "chroma")
        # A different embedding model must never silently reuse incompatible vectors.
        version = hashlib.sha256(self.settings.embedding_model.encode()).hexdigest()[:16]
        self.collection = self.store.collection(f"preferences_{version}")
        self._ready = True

    async def initialize(self) -> None:
        """Warm models at startup; configuration errors fail visibly."""
        try:
            await self.worker.run(self._initialize)
        except Exception as exc:
            raise ServiceUnavailable("Não foi possível iniciar a memória. Verifique o modelo de embeddings e o diretório de dados.") from exc

    def _recall(self, owner: str, text: str) -> list[str]:
        if not self._ready:
            raise RuntimeError("Memória não inicializada.")
        results = self.collection.query(query_embeddings=[self.embeddings.encode(text)],
            n_results=self.settings.memory_top_k, where={"owner": owner},
            include=["documents"])
        return [str(doc)[:2000] for doc in (results.get("documents") or [[]])[0]]

    async def recall(self, owner: str, query: str) -> list[str]:
        """Retrieve only this user's stored preferences."""
        return await self.worker.run(self._recall, owner, query)

    def _remember(self, owner: str, text: str) -> str:
        key = hashlib.sha256(f"{owner}\0{text}".encode()).hexdigest()
        self.collection.upsert(ids=[key], documents=[text],
            embeddings=[self.embeddings.encode(text)], metadatas=[{"owner": owner}])
        return key

    async def remember(self, owner: str, text: str) -> str:
        """Persist explicitly requested text; identical writes are idempotent."""
        if not text.strip() or len(text) > 2000:
            raise ValueError("Preferência deve conter entre 1 e 2000 caracteres.")
        return await self.worker.run(self._remember, owner, text.strip())

    def _forget(self, owner: str) -> None:
        for collection in self.store.client.list_collections():
            if collection.name.startswith("preferences_"):
                self.store.client.get_collection(collection.name).delete(where={"owner": owner})

    async def forget(self, owner: str) -> None:
        """Remove this user's preferences from all application embedding collections."""
        await self.worker.run(self._forget, owner)

    async def aclose(self) -> None:
        """Drain native work. PersistentClient owns process-lifetime native resources."""
        await self.worker.aclose()


class DisabledMemory:
    """Explicit no-memory mode, useful for constrained machines and diagnostics."""

    async def recall(self, owner: str, query: str) -> list[str]:
        return []

    async def remember(self, owner: str, text: str) -> str:
        raise ServiceUnavailable("Memória desativada na configuração.")

    async def forget(self, owner: str) -> None:
        raise ServiceUnavailable("Memória desativada na configuração.")

    async def aclose(self) -> None:
        return None
