import httpx
from ollama import ResponseError

from app.core.provider_diagnostics import inspect_provider, provider_error


def test_provider_error_is_actionable_and_redacted(settings):
    for status, expected in [(404, '404'), (400, '400'), (500, 'servidor')]:
        message = provider_error(ResponseError('secret-prompt-and-token', status), settings)
        assert expected in message
        assert 'secret-prompt' not in message
    assert 'tempo limite' in provider_error(TimeoutError(), settings)
    assert 'conectar' in provider_error(httpx.ConnectError('secret'), settings)


async def test_ollama_inventory_reports_missing_model(settings, monkeypatch):
    async def get(self, url):
        return httpx.Response(200, json={'models': [{'name': 'other:latest'}]}, request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = await inspect_provider(settings)
    assert result['status'] == 'missing_model'
    assert 'api_token' not in result
