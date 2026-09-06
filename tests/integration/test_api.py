from types import SimpleNamespace

import httpx
import pytest

from app.api.server import create_app
from app.core.schemas import ChatResponse


async def test_api_auth_body_limits_and_trusted_identity(settings):
    calls = []

    class Agent:
        async def chat(self, owner, session, text):
            calls.append((owner, session, text))
            return ChatResponse(text="Olá")

    async def close():
        calls.append("closed")

    async def factory(_):
        return SimpleNamespace(agent=Agent(), aclose=close)

    app = create_app(settings, factory)
    token = settings.api_token.get_secret_value()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.post("/chat", json={"message": "Oi"})).status_code == 401
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.post("/chat", json={"message": "Oi", "session_id": "abc"}, headers=headers)
            assert response.status_code == 200
            assert calls == [("owner", "abc", "Oi")]
            assert (await client.post("/chat", json={"message": "Oi", "owner": "other"}, headers=headers)).status_code == 422
            assert (await client.post("/chat", content=b"x" * 70000, headers=headers)).status_code == 413
            assert (await client.post("/chat", json={"message": " "}, headers=headers)).status_code == 422
    assert calls[-1] == "closed"


def test_api_refuses_missing_auth_token(settings):
    settings.api_token = None
    with pytest.raises(ValueError, match="API_TOKEN"):
        create_app(settings)
