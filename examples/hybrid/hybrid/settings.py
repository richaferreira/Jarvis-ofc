"""Independent settings for the opt-in realtime service."""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    owner: str = Field(default="casa01", pattern=r"^[a-z0-9_-]{1,40}$")
    api_token: SecretStr = Field(min_length=32)
    origins: list[str] = ["http://localhost:3000"]
    llm_provider: Literal["openai", "gemini", "ollama"] = "ollama"
    llm_model: str = "qwen3:8b"
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    ollama_url: str = "http://host.docker.internal:11434"
    embedding_model: str = "embeddinggemma"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr
    neo4j_database: str = "neo4j"
    mqtt_host: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_user: str = "jarvis"
    mqtt_password: SecretStr
    mqtt_tls: bool = False
    mqtt_device_ids: list[str] = Field(default_factory=lambda: ["tuya_qd01_c03"])
    retrieval_timeout: float = Field(default=5, gt=0, le=30)
    response_timeout: float = Field(default=90, ge=1, le=300)
    telemetry_ttl: float = Field(default=30, ge=1, le=600)
    max_connections: int = Field(default=16, ge=1, le=128)

    @model_validator(mode="after")
    def valid_devices(self) -> Self:
        import re

        if len(self.mqtt_device_ids) > 256 or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", device) for device in self.mqtt_device_ids
        ):
            raise ValueError("Lista de dispositivos inválida.")
        return self
