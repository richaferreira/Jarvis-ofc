"""WebSocket with independent receive/send, stream cancellation and state events."""

import asyncio
import hmac
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel, Field, ValidationError

from hybrid.graph import HybridAgent
from hybrid.mqtt import MQTTService, StateHub
from hybrid.retrieval import ChromaRepository, Neo4jRepository
from hybrid.settings import Settings

log = logging.getLogger(__name__)


class ClientFrame(BaseModel):
    type: Literal["auth", "user", "barge_in"]
    token: str = Field(default="", max_length=256)
    text: str = Field(default="", max_length=4000)


def create_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        if settings.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY ausente.")
        return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key,
                          streaming=True, timeout=30, max_retries=0, max_completion_tokens=1024)
    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if settings.google_api_key is None:
            raise ValueError("GOOGLE_API_KEY ausente.")
        return ChatGoogleGenerativeAI(model=settings.llm_model, google_api_key=settings.google_api_key,
                                      max_output_tokens=1024, timeout=30, max_retries=0)
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_url,
                      num_predict=1024, client_kwargs={"timeout": 30})


async def cancel(task: asyncio.Task[None] | None) -> None:
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class SocketSession:
    def __init__(self, socket: WebSocket, agent: HybridAgent, hub: StateHub, settings: Settings) -> None:
        self.socket, self.agent, self.hub, self.settings = socket, agent, hub, settings
        self.generation = ""
        self.answer_task: asyncio.Task[None] | None = None
        self.send_lock = asyncio.Lock()

    async def send(self, event: dict[str, object], generation: str | None = None) -> None:
        async with self.send_lock:
            if generation is not None and generation != self.generation:
                return
            async with asyncio.timeout(5):
                await self.socket.send_json({**event, **({"generation": generation} if generation else {})})

    async def stop_answer(self) -> None:
        self.generation = secrets.token_urlsafe(12)  # Invalida tokens em trânsito antes de cancelar.
        task, self.answer_task = self.answer_task, None
        await cancel(task)

    async def respond(self, text: str, generation: str) -> None:
        try:
            async with asyncio.timeout(self.settings.response_timeout):
                async for event in self.agent.stream(self.settings.owner, text):
                    await self.send(event, generation)
            await self.send({"type": "done"}, generation)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("stream_failed", extra={"error_type": type(exc).__name__})
            with suppress(Exception):
                await self.send({"type": "error", "message": "Resposta interrompida ou provedor indisponível."}, generation)

    async def telemetry(self) -> None:
        async with self.hub.subscribe() as queue:
            await self.send({"type": "snapshot", "devices": self.hub.snapshot()})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5)
                    await self.send({"type": "device_state", "device": event})
                except TimeoutError:
                    # Reavalia TTL/conexão, sem polling HTTP de hardware.
                    await self.send({"type": "snapshot", "devices": self.hub.snapshot()})

    async def receive(self) -> None:
        while True:
            raw = await self.socket.receive_text()
            if len(raw.encode()) > 8192:
                await self.socket.close(code=1009)
                return
            try:
                frame = ClientFrame.model_validate_json(raw)
            except ValidationError:
                await self.send({"type": "error", "message": "Frame inválido."})
                continue
            if frame.type == "barge_in":
                await self.stop_answer()
                # Cliente já deve ter silenciado TTS/playback local ao detectar fala.
                await self.send({"type": "interrupted", "generation": self.generation})
            elif frame.type == "user" and frame.text.strip():
                await self.stop_answer()
                await self.send({"type": "started", "generation": self.generation})
                self.answer_task = asyncio.create_task(self.respond(frame.text, self.generation))

    async def run(self) -> None:
        receiver = asyncio.create_task(self.receive())
        telemetry = asyncio.create_task(self.telemetry())
        try:
            done, _ = await asyncio.wait({receiver, telemetry}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            await self.stop_answer()
            for task in (receiver, telemetry):
                task.cancel()
            await asyncio.gather(receiver, telemetry, return_exceptions=True)


def create_app() -> FastAPI:
    settings = Settings()
    slots = asyncio.Semaphore(settings.max_connections)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            driver = AsyncGraphDatabase.driver(settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
                max_connection_pool_size=16, connection_timeout=5)
            stack.push_async_callback(driver.close)
            await driver.verify_connectivity()
            embeddings = OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_url)
            async with asyncio.timeout(30):
                vectors = await ChromaRepository.connect(settings.chroma_host, settings.chroma_port,
                                                         settings.embedding_model, embeddings)
            hub = StateHub(settings.mqtt_device_ids, settings.telemetry_ttl)
            mqtt = asyncio.create_task(MQTTService(settings, hub).run())
            stack.push_async_callback(cancel, mqtt)
            app.state.hub = hub
            app.state.agent = HybridAgent(create_model(settings), vectors,
                Neo4jRepository(driver, settings.neo4j_database), hub, settings.retrieval_timeout)
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"ready": True, "mqtt_connected": app.state.hub.connected}

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        origin = socket.headers.get("origin")
        if origin is not None and origin not in settings.origins:
            await socket.close(code=1008)
            return
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.05)
        except TimeoutError:
            await socket.close(code=1013)
            return
        try:
            await socket.accept()
            async with asyncio.timeout(5):
                frame = ClientFrame.model_validate_json(await socket.receive_text())
            if frame.type != "auth" or not hmac.compare_digest(frame.token.encode(), settings.api_token.get_secret_value().encode()):
                await socket.close(code=1008)
                return
            await socket.send_json({"type": "ready"})
            await SocketSession(socket, app.state.agent, app.state.hub, settings).run()
        except (WebSocketDisconnect, TimeoutError, ValidationError):
            with suppress(Exception):
                await socket.close(code=1008)
        finally:
            slots.release()

    return app
