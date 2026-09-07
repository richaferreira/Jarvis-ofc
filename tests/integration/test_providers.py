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
