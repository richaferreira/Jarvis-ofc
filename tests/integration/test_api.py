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


async def test_dashboard_assets_and_status_auth(settings, monkeypatch):
    async def inspect(_):
        return {'status': 'missing_model', 'model': 'test-model'}
    monkeypatch.setattr('app.api.server.inspect_provider', inspect)
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        page = await client.get('/')
        assert page.status_code == 200
        assert 'lang="pt-BR"' in page.text
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert settings.api_token.get_secret_value() not in page.text
        assert (await client.get('/assets/app.js')).status_code == 200
        assert (await client.get('/system/status')).status_code == 401
        status = await client.get('/system/status', headers={'Authorization': f'Bearer {settings.api_token.get_secret_value()}'})
        assert status.json()['status'] == 'missing_model'
