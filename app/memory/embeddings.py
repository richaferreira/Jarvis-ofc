"""Explicit local multilingual embeddings, loaded once during startup."""

from pathlib import Path


class LocalEmbeddings:
    """SentenceTransformers adapter; use from the serialized memory worker."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, cache_folder=str(cache_dir),
                                         device="cpu", trust_remote_code=False)

    def encode(self, text: str) -> list[float]:
        """Return normalized vectors for consistent cosine retrieval."""
        return self.model.encode(text, normalize_embeddings=True).tolist()
