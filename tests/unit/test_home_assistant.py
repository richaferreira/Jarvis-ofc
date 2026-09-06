import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.exceptions import ActionError
from app.infrastructure.http_client import HttpClient
from app.tools.home_assistant import HomeAssistantService


def configuration():
    return Settings(_env_file=None, home_assistant_url="http://127.0.0.1:8123",
        home_assistant_token="secret-test-token", home_actions={
            "ligar_sala": {"description": "Ligar luz", "domain": "light", "service": "turn_on", "entity_ids": ["light.sala"]},
            "cena": {"description": "Cena", "webhook_id": "test_webhook_12345"}})


async def test_proposal_is_inert_and_confirmation_is_scoped_and_single_use():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=[])

    http = HttpClient(2, httpx.MockTransport(handle))
    home = HomeAssistantService(configuration(), http)
    proposal = await home.propose("ligar_sala", "owner", "s1")
    assert not calls
    with pytest.raises(ActionError):
        await home.confirm(proposal["token"], "intruder", "s1")
    with pytest.raises(ActionError):
        await home.confirm(proposal["token"], "owner", "s2")
    results = await asyncio.gather(home.confirm(proposal["token"], "owner", "s1"),
                                   home.confirm(proposal["token"], "owner", "s1"), return_exceptions=True)
    assert sum(isinstance(r, ActionError) for r in results) == 1
    assert len(calls) == 1
    assert calls[0].url.path == "/api/services/light/turn_on"
    assert json.loads(calls[0].content) == {"entity_id": ["light.sala"]}
    assert calls[0].headers["authorization"] == "Bearer secret-test-token"
    await http.aclose()


async def test_post_timeout_consumes_confirmation_without_retry():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("ambiguous", request=request)

    http = HttpClient(2, httpx.MockTransport(handle))
    home = HomeAssistantService(configuration(), http)
    proposal = await home.propose("cena", "owner", "s")
    with pytest.raises(ActionError, match="Resultado incerto"):
        await home.confirm(proposal["token"], "owner", "s")
    with pytest.raises(ActionError):
        await home.confirm(proposal["token"], "owner", "s")
    assert len(calls) == 1
    assert "authorization" not in calls[0].headers
    assert "test_webhook" not in json.dumps(home.catalog())
    await http.aclose()


async def test_unknown_expired_and_cleared_intents_are_rejected(monkeypatch):
    http = HttpClient(2, httpx.MockTransport(lambda r: httpx.Response(200)))
    home = HomeAssistantService(configuration(), http)
    with pytest.raises(ActionError):
        await home.propose("arbitrary_url", "owner", "s")
    proposal = await home.propose("cena", "owner", "s")
    from app.tools import home_assistant

    now = home_assistant.time.monotonic()
    monkeypatch.setattr(home_assistant.time, "monotonic", lambda: now + 1000)
    with pytest.raises(ActionError):
        await home.confirm(proposal["token"], "owner", "s")
    other = await home.propose("cena", "owner", "s")
    await home.clear_session("owner", "s")
    with pytest.raises(ActionError):
        await home.confirm(other["token"], "owner", "s")
    await http.aclose()
