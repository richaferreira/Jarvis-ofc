"""Construct actual provider adapters without sending network requests."""

import pytest
from pydantic import SecretStr

from app.core.model_factory import ModelFactory
from app.runtime import Runtime


@pytest.mark.parametrize("provider,model", [("omniroute", "test-model"), ("openai", "test-model"), ("gemini", "test-model"), ("ollama", "test-model")])
async def test_factory_constructs_configured_sdk_adapter(settings, provider, model):
    settings.llm_provider = provider
    settings.llm_model = model
    settings.openai_api_key = SecretStr("sk-test-placeholder-not-a-real-key")
    settings.google_api_key = SecretStr("test-placeholder-not-a-real-key")
    settings.omniroute_api_key = SecretStr("test-gateway-key")
    adapter = ModelFactory.create(settings)
    assert callable(adapter.ainvoke)
    assert callable(adapter.bind_tools)
    runtime = Runtime(settings)
    runtime.model = adapter
    await runtime._close_model()


async def test_gateway_chat_uses_compatible_endpoint(settings, monkeypatch):
    import httpx
    import langchain_openai
    from langchain_core.messages import HumanMessage

    settings.llm_provider = 'omniroute'
    settings.omniroute_api_key = SecretStr('gateway-test-key')
    captured = []

    def respond(request):
        captured.append(request)
        assert str(request.url) == 'http://127.0.0.1:20128/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer gateway-test-key'
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'test-model',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Olá pelo gateway'}, 'finish_reason': 'stop'}],
        })

    original = langchain_openai.ChatOpenAI
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kwargs: original(**kwargs, http_async_client=client))
        adapter = ModelFactory.create(settings)
        try:
            reply = await adapter.ainvoke([HumanMessage(content='Olá')])
            assert reply.content == 'Olá pelo gateway'
            assert len(captured) == 1
        finally:
            runtime = Runtime(settings)
            runtime.model = adapter
            await runtime._close_model()
