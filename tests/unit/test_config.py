import pytest
from pydantic import ValidationError

from app.config import HomeAction, Settings


def test_dotenv_loads_and_secrets_are_masked(tmp_path):
    env = tmp_path / "test.env"
    env.write_text("LLM_PROVIDER=openai\nOPENAI_API_KEY=secret-test-value\nTIMEZONE=UTC\n")
    settings = Settings(_env_file=env)
    assert settings.llm_provider == "openai"
    assert settings.openai_api_key.get_secret_value() == "secret-test-value"
    assert "secret-test-value" not in repr(settings)


@pytest.mark.parametrize("url", ["file:///tmp/x", "http://user:pass@localhost", "http://localhost?token=x", "https://localhost/#fragment"])
def test_reject_unsafe_configured_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, home_assistant_url=url)


def test_action_requires_fixed_target_and_credentials():
    with pytest.raises(ValidationError):
        HomeAction(description="test", domain="light", service="turn_on")
    with pytest.raises(ValidationError):
        HomeAction(description="test", webhook_id="abcdefgh", domain="light")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, home_assistant_url="http://localhost:8123",
                 home_actions={"on": {"description": "Luz", "domain": "light", "service": "turn_on", "entity_ids": ["light.sala"]}})


def test_reject_bad_timezone_and_audio_rate():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, timezone="Invalid/Zone")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, audio_sample_rate=44100)
