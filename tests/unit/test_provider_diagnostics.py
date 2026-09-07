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


async def test_gateway_catalog_uses_server_key(settings, monkeypatch):
    from pydantic import SecretStr
    settings.llm_provider = 'omniroute'
    settings.omniroute_api_key = SecretStr('gateway-secret')
    async def get(self, url, **kwargs):
        assert url == 'http://127.0.0.1:20128/v1/models'
        assert kwargs['headers']['Authorization'] == 'Bearer gateway-secret'
        return httpx.Response(200, json={'data': [{'id': 'provider/model'}]}, request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = await inspect_provider(settings)
    assert result['models'] == ['provider/model']
    assert 'gateway-secret' not in str(result)


async def test_gateway_rejected_key_is_redacted(settings, monkeypatch):
    from pydantic import SecretStr
    settings.llm_provider = 'omniroute'
    settings.omniroute_api_key = SecretStr('gateway-secret')
    async def get(self, url, **kwargs):
        return httpx.Response(401, text='gateway-secret', request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = await inspect_provider(settings)
    assert result['status'] == 'unauthorized'
    assert 'gateway-secret' not in str(result)
