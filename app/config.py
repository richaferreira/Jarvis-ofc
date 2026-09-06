"""Validated environment configuration; constructing Settings has no network effects."""

import re
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HomeAction(BaseModel):
    """A trusted administrator-defined action, never an LLM-provided URL or payload."""

    model_config = {"extra": "forbid"}
    description: str = Field(min_length=1, max_length=200)
    domain: str | None = None
    service: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    webhook_id: SecretStr | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        """Allow a service with explicit entities OR a webhook, exclusively."""
        if self.webhook_id is not None:
            if self.domain or self.service or self.entity_ids:
                raise ValueError("Webhook não pode conter serviço ou entidades.")
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", self.webhook_id.get_secret_value()):
                raise ValueError("Identificador de webhook inválido.")
        else:
            if not self.domain or not self.service or not self.entity_ids:
                raise ValueError("Ação REST exige domain, service e entity_ids.")
            for value in (self.domain, self.service):
                if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
                    raise ValueError("Serviço inválido.")
            for entity in self.entity_ids:
                if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z0-9_]+", entity):
                    raise ValueError("Entidade inválida.")
        return self


class Settings(BaseSettings):
    """Runtime settings loaded by python-dotenv through pydantic-settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    llm_provider: Literal["openai", "gemini", "ollama"] = "ollama"
    llm_model: str = "qwen3:8b"
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_max_tokens: int = Field(default=1024, ge=64, le=8192)
    request_timeout: float = Field(default=30, ge=1, le=120)
    turn_timeout: float = Field(default=120, ge=5, le=600)
    max_tool_rounds: int = Field(default=3, ge=1, le=8)
    max_tool_calls: int = Field(default=4, ge=1, le=8)
    max_input_chars: int = Field(default=4000, ge=100, le=16000)
    timezone: str = "America/Sao_Paulo"
    data_dir: Path = Path("data")
    memory_enabled: bool = True
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    memory_top_k: int = Field(default=3, ge=1, le=10)
    history_turns: int = Field(default=8, ge=1, le=30)
    history_chars: int = Field(default=12000, ge=1000, le=50000)
    max_sessions: int = Field(default=64, ge=1, le=1000)
    session_ttl: int = Field(default=3600, ge=60)
    whisper_model: Literal["base", "small"] = "base"
    whisper_device: Literal["cpu", "cuda"] = "cpu"
    whisper_language: str = "pt"
    audio_device: int | None = None
    audio_sample_rate: int = 16000
    speech_threshold: float = Field(default=0.015, gt=0, lt=1)
    silence_seconds: float = Field(default=1.2, ge=0.3, le=5)
    listen_timeout: float = Field(default=10, ge=1, le=60)
    max_record_seconds: float = Field(default=20, ge=2, le=60)
    tts_provider: Literal["edge", "elevenlabs"] = "edge"
    edge_voice: str = "pt-BR-AntonioNeural"
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"
    tts_max_chars: int = Field(default=3000, ge=100, le=10000)
    tts_cache_mb: int = Field(default=128, ge=8, le=2048)
    tts_cache_ttl: int = Field(default=604800, ge=60)
    home_assistant_url: str | None = None
    home_assistant_token: SecretStr | None = None
    home_actions: dict[str, HomeAction] = Field(default_factory=dict)
    action_ttl: int = Field(default=120, ge=15, le=600)
    api_token: SecretStr | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        """Reject timezone names unavailable to zoneinfo."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuso horário desconhecido.") from exc
        return value

    @field_validator("ollama_base_url", "home_assistant_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        """Reject credentials, query strings, fragments and non-HTTP transports."""
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("URL HTTP(S) inválida; use credenciais nos campos próprios.")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_invariants(self) -> Self:
        """Validate constraints shared by API and desktop modes."""
        if self.audio_sample_rate != 16000:
            raise ValueError("Whisper recebe áudio mono a 16000 Hz neste projeto.")
        if self.silence_seconds >= self.max_record_seconds:
            raise ValueError("Silêncio deve ser menor que a duração máxima da gravação.")
        for name in self.home_actions:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
                raise ValueError("Nome de ação inválido.")
        if self.home_actions and not self.home_assistant_url:
            raise ValueError("HOME_ACTIONS exige HOME_ASSISTANT_URL.")
        if any(a.webhook_id is None for a in self.home_actions.values()):
            if not self.home_assistant_token or not self.home_assistant_token.get_secret_value():
                raise ValueError("Ações REST exigem HOME_ASSISTANT_TOKEN.")
        return self
