"""Authenticated, single-user HTTP interface; no microphone access in server mode."""

import asyncio
import hmac
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.core.schemas import ChatRequest, ChatResponse, ConfirmationRequest, PreferenceRequest
from app.exceptions import ActionError, BusyError, JarvisError
from app.logging_config import configure_logging
from app.runtime import Runtime

logger = structlog.get_logger()


class BodyLimitMiddleware:
    """Bound HTTP body bytes and upload duration before JSON decoding."""

    def __init__(self, app: ASGIApp, limit: int = 65536) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > self.limit:
                        await JSONResponse({"detail": "Corpo da requisição excedeu o limite."}, 413)(scope, receive, send)
                        return
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "Tempo de envio excedido."}, 408)(scope, receive, send)
            return
        delivered = False

        async def replay() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None,
               runtime_factory: Callable[..., Any] = Runtime.create) -> FastAPI:
    """Build an API requiring a dedicated token (minimum 32 characters)."""
    settings = settings or Settings()
    token = settings.api_token.get_secret_value() if settings.api_token else ""
    if len(token) < 32:
        raise ValueError("Configure API_TOKEN com pelo menos 32 caracteres aleatórios.")
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = await runtime_factory(settings)
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(title="J.A.R.V.I.S.", version="1.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimitMiddleware)
    bearer = HTTPBearer(auto_error=False)

    async def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or not hmac.compare_digest(credentials.credentials.encode(), token.encode()):
            raise HTTPException(401, "Credenciais inválidas.", headers={"WWW-Authenticate": "Bearer"})
        return "owner"  # One configured principal. Clients cannot select another user's identity.

    @app.exception_handler(JarvisError)
    async def handle_known_error(request: Request, exc: JarvisError) -> JSONResponse:
        status = 429 if isinstance(exc, BusyError) else 409 if isinstance(exc, ActionError) else 503
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.exception_handler(Exception)
    async def handle_unknown_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("api_failed", error_type=type(exc).__name__)
        return JSONResponse({"detail": "Falha interna. Consulte os eventos de diagnóstico."}, 500)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ready"}  # Startup readiness, not an external-provider availability probe.

    @app.post("/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request, owner: str = Depends(authenticate)) -> ChatResponse:
        if not body.message.strip() or len(body.message) > settings.max_input_chars:
            raise HTTPException(422, "Mensagem vazia ou acima do limite configurado.")
        return await request.app.state.runtime.agent.chat(owner, body.session_id, body.message)

    @app.post("/actions/confirm")
    async def confirm(body: ConfirmationRequest, request: Request, owner: str = Depends(authenticate)) -> dict[str, str]:
        async with asyncio.timeout(settings.request_timeout):
            return await request.app.state.runtime.home.confirm(body.token, owner, body.session_id)

    @app.post("/memory")
    async def remember(body: PreferenceRequest, request: Request, owner: str = Depends(authenticate)) -> dict[str, str]:
        if not body.text.strip():
            raise HTTPException(422, "Preferência vazia.")
        async with asyncio.timeout(settings.request_timeout):
            key = await request.app.state.runtime.memory.remember(owner, body.text)
        return {"id": key, "status": "stored"}

    @app.delete("/memory")
    async def forget(request: Request, owner: str = Depends(authenticate)) -> dict[str, str]:
        async with asyncio.timeout(settings.request_timeout):
            await request.app.state.runtime.memory.forget(owner)
        return {"status": "deleted"}

    @app.delete("/sessions/{session_id}")
    async def clear(session_id: str, request: Request, owner: str = Depends(authenticate)) -> dict[str, str]:
        async with asyncio.timeout(settings.turn_timeout + 1):
            await request.app.state.runtime.agent.clear(owner, session_id)
        return {"status": "cleared"}

    return app
