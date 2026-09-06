"""Process-local Singleton owning the embedded Chroma client."""

import threading
from pathlib import Path
from typing import Any


class VectorStore:
    """One embedded database per process. Multiple writers require a Chroma server."""

    _instance: "VectorStore | None" = None
    _lock = threading.Lock()

    def __new__(cls, path: Path) -> "VectorStore":
        """Initialize exactly once and reject accidental cross-directory reuse."""
        resolved = path.resolve()
        with cls._lock:
            if cls._instance is None:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                instance = super().__new__(cls)
                instance.path = resolved
                instance.client = chromadb.PersistentClient(
                    path=str(resolved), settings=ChromaSettings(anonymized_telemetry=False))
                cls._instance = instance
            elif cls._instance.path != resolved:
                raise RuntimeError("Singleton Chroma já inicializado em outro diretório.")
            return cls._instance

    def collection(self, name: str) -> Any:
        """Use explicit application-generated embeddings instead of implicit downloads."""
        return self.client.get_or_create_collection(
            name=name, embedding_function=None, metadata={"hnsw:space": "cosine"})
