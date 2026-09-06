"""Edge-TTS and ElevenLabs synthesis with bounded output and persistent caching."""

import asyncio
from typing import Protocol

import structlog

from app.config import Settings
from app.exceptions import ServiceUnavailable
from app.infrastructure.audio_cache import AudioCache
from app.infrastructure.http_client import HttpClient

logger = structlog.get_logger()
MAX_AUDIO_BYTES = 12 * 1024 * 1024


class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


class EdgeProvider:
    """Microsoft Edge online speech accessed through edge-tts."""

    def __init__(self, voice: str) -> None:
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        data = bytearray()
        async for chunk in edge_tts.Communicate(text, self.voice).stream():
            if chunk["type"] == "audio":
                data.extend(chunk["data"])
                if len(data) > MAX_AUDIO_BYTES:
                    raise ServiceUnavailable("Áudio sintetizado excedeu o limite.")
        return bytes(data)


class ElevenLabsProvider:
    """Premium TTS using the public REST API and the shared asynchronous client."""

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings, self.http = settings, http
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            raise ServiceUnavailable("Configure ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID.")
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", settings.elevenlabs_voice_id):
            raise ServiceUnavailable("ELEVENLABS_VOICE_ID inválido.")

    async def synthesize(self, text: str) -> bytes:
        assert self.settings.elevenlabs_api_key is not None
        data = bytearray()
        async with self.http.client.stream("POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.settings.elevenlabs_voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.settings.elevenlabs_api_key.get_secret_value(),
                     "Accept": "audio/mpeg"},
            json={"text": text, "model_id": self.settings.elevenlabs_model}) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_AUDIO_BYTES:
                    raise ServiceUnavailable("Áudio sintetizado excedeu o limite.")
        return bytes(data)


class SpeechSynthesizer:
    """Cache-aware synthesis. Cache failures do not discard valid generated speech."""

    def __init__(self, settings: Settings, cache: AudioCache, provider: TTSProvider) -> None:
        self.settings, self.cache, self.provider = settings, cache, provider
        self._lock = asyncio.Lock()

    async def synthesize(self, text: str) -> bytes:
        """Limit spoken text while preserving the complete textual answer in the UI."""
        text = text.strip()
        if not text:
            raise ValueError("Texto vazio para síntese.")
        if len(text) > self.settings.tts_max_chars:
            text = text[:self.settings.tts_max_chars].rsplit(" ", 1)[0] + ". A resposta completa está na tela."
        key = self.cache.key(text=text, provider=self.settings.tts_provider,
            voice=self.settings.edge_voice if self.settings.tts_provider == "edge" else self.settings.elevenlabs_voice_id,
            model=self.settings.elevenlabs_model if self.settings.tts_provider == "elevenlabs" else "edge",
            format="mp3", rate="default", schema="1")
        async with self._lock:
            try:
                cached = await self.cache.get(key)
            except Exception as exc:
                logger.warning("tts_cache_read_failed", error_type=type(exc).__name__)
                cached = None
            if cached:
                return cached
            try:
                async with asyncio.timeout(self.settings.request_timeout):
                    data = await self.provider.synthesize(text)
                if not data:
                    raise ServiceUnavailable("O provedor de voz retornou áudio vazio.")
            except Exception as exc:
                raise ServiceUnavailable("Síntese de voz indisponível. A resposta permanece na tela.") from exc
            try:
                await self.cache.put(key, data)
            except Exception as exc:
                logger.warning("tts_cache_write_failed", error_type=type(exc).__name__)
            return data
