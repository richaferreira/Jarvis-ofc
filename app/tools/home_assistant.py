"""Home Assistant actions require a separate, explicit confirmation outside the LLM."""

import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.config import HomeAction, Settings
from app.exceptions import ActionError
from app.infrastructure.http_client import HttpClient

logger = structlog.get_logger()


@dataclass(frozen=True)
class PendingAction:
    """Immutable server-side intent bound to a user and conversation."""

    token: str
    owner: str
    session: str
    alias: str
    target: HomeAction
    expires_at: float


class HomeAssistantService:
    """Only execute configured targets; consume confirmation tokens exactly once."""

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http
        self._pending: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()

    def catalog(self) -> dict[str, str]:
        """Expose descriptions, never webhook secrets or authorization headers."""
        return {name: action.description for name, action in self.settings.home_actions.items()}

    def _purge(self) -> None:
        now = time.monotonic()
        self._pending = {k: v for k, v in self._pending.items() if v.expires_at > now}

    async def propose(self, alias: str, owner: str, session: str) -> dict[str, Any]:
        """Create an expiring intent; this method has no external side effects."""
        async with self._lock:
            self._purge()
            target = self.settings.home_actions.get(alias)
            if target is None:
                raise ActionError("Ação não está na lista permitida.")
            existing = next((p for p in self._pending.values()
                             if (p.owner, p.session, p.alias) == (owner, session, alias)), None)
            if existing is None:
                if len(self._pending) >= 128:
                    raise ActionError("Há muitas ações pendentes. Aguarde a expiração.")
                token = secrets.token_urlsafe(24)
                existing = PendingAction(token, owner, session, alias,
                                         target.model_copy(deep=True),
                                         time.monotonic() + self.settings.action_ttl)
                self._pending[token] = existing
            return {"status": "confirmation_required", "token": existing.token,
                    "action": alias, "description": target.description,
                    "expires_in_seconds": max(0, int(existing.expires_at - time.monotonic()))}

    async def confirm(self, token: str, owner: str, session: str) -> dict[str, str]:
        """Send one POST only. A timeout is an unknown outcome, never a failed-action retry."""
        async with self._lock:
            self._purge()
            intent = self._pending.get(token)
            if intent is None or (intent.owner, intent.session) != (owner, session):
                raise ActionError("Confirmação inválida, expirada ou já utilizada.")
            del self._pending[token]
        target = intent.target
        base = self.settings.home_assistant_url
        if not base:
            raise ActionError("Home Assistant não configurado.")
        headers = {"Content-Type": "application/json"}
        if target.webhook_id:
            url = f"{base}/api/webhook/{target.webhook_id.get_secret_value()}"
            payload: dict[str, Any] = {}
        else:
            url = f"{base}/api/services/{target.domain}/{target.service}"
            credential = self.settings.home_assistant_token
            if credential is None:
                raise ActionError("Token do Home Assistant não configurado.")
            headers["Authorization"] = f"Bearer {credential.get_secret_value()}"
            payload = {"entity_id": target.entity_ids}
        try:
            # Stream only headers: do not retain or log sensitive state response bodies.
            async with self.http.client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("home_action_http_error", status=exc.response.status_code)
            raise ActionError("Home Assistant não confirmou a solicitação. Verifique o dispositivo antes de tentar novamente.") from exc
        except (httpx.RequestError, asyncio.CancelledError) as exc:
            logger.warning("home_action_outcome_unknown", action=intent.alias)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise ActionError("Resultado incerto: a solicitação pode ter sido executada. Verifique o dispositivo; a confirmação foi consumida.") from exc
        logger.info("home_action_accepted", action=intent.alias)
        return {"status": "accepted", "action": intent.alias,
                "message": "Home Assistant aceitou a solicitação; o estado físico não foi verificado."}

    async def clear_session(self, owner: str, session: str) -> None:
        """Invalidate outstanding intents when a conversation is cleared."""
        async with self._lock:
            self._pending = {k: p for k, p in self._pending.items()
                             if (p.owner, p.session) != (owner, session)}
