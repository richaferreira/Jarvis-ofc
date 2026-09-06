"""Hermetic fixtures: no credentials, downloads, microphone or IoT side effects."""

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, memory_enabled=False, data_dir=tmp_path,
                    llm_provider="ollama", llm_model="test-model",
                    api_token="test-token-" + "x" * 40)
