"""Composition root and explicit resource lifecycle shared by CLI and API."""

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from app.config import Settings
from app.core.agent import JarvisAgent
from app.core.model_factory import ModelFactory
from app.infrastructure.http_client import HttpClient
from app.memory.memory import DisabledMemory, MemoryService
from app.tools.home_assistant import HomeAssistantService
from app.tools.tools import ToolRegistry
from app.tools.weather import WeatherService
from app.tools.web_search import WebSearch


class Runtime:
    """Own every service; partially initialized runtimes are cleaned up on failure."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack = AsyncExitStack()

    @classmethod
    async def create(cls, settings: Settings) -> "Runtime":
        """Construct headless services and warm persistent memory when enabled."""
        self = cls(settings)
        try:
            self.http = HttpClient(settings.request_timeout)
            self._stack.push_async_callback(self.http.aclose)
            self.search = WebSearch(settings.request_timeout)
            self._stack.push_async_callback(self.search.aclose)
            self.memory = MemoryService(settings) if settings.memory_enabled else DisabledMemory()
            self._stack.push_async_callback(self.memory.aclose)
            if isinstance(self.memory, MemoryService):
                await self.memory.initialize()
            self.home = HomeAssistantService(settings, self.http)
            registry = ToolRegistry(settings, self.search, WeatherService(self.http), self.home)
            self.model = ModelFactory.create(settings)
            self._stack.push_async_callback(self._close_model)
            self.agent = JarvisAgent(settings, self.model, self.memory, registry)
            return self
        except BaseException:
            await self._stack.aclose()
            raise

    async def _close_model(self) -> None:
        """Close exposed provider transports without depending on private SDK attributes."""
        # OpenAI exposes its root clients; Gemini/Ollama own SDK lifecycle internally.
        async_client = getattr(self.model, "root_async_client", None)
        sync_client = getattr(self.model, "root_client", None)
        if async_client is not None:
            await async_client.close()
        if sync_client is not None:
            await asyncio.to_thread(sync_client.close)

    async def enable_audio(self) -> None:
        """Import and initialize desktop audio only when voice mode is selected."""
        from app.audio.player import AudioPlayer
        from app.audio.recorder import MicrophoneRecorder
        from app.audio.stt import WhisperSTT
        from app.audio.tts import EdgeProvider, ElevenLabsProvider, SpeechSynthesizer
        from app.infrastructure.audio_cache import AudioCache

        self.player = AudioPlayer()
        self.recorder = MicrophoneRecorder(self.settings)
        self._stack.push_async_callback(self.recorder.aclose)
        self.stt = WhisperSTT(self.settings)
        self._stack.push_async_callback(self.stt.aclose)
        cache = AudioCache(self.settings.data_dir / "cache" / "tts",
                           self.settings.tts_cache_mb, self.settings.tts_cache_ttl)
        self._stack.push_async_callback(cache.aclose)
        provider: Any = EdgeProvider(self.settings.edge_voice) if self.settings.tts_provider == "edge" else ElevenLabsProvider(self.settings, self.http)
        self.tts = SpeechSynthesizer(self.settings, cache, provider)
        await self.stt.initialize()

    async def aclose(self) -> None:
        """Close resources in reverse initialization order."""
        await self._stack.aclose()
