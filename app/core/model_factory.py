"""Factory for lazily imported model providers."""

from typing import Any

from app.config import Settings
from app.exceptions import JarvisError


class ModelFactory:
    """Create one configured model without exposing secrets in representations."""

    @staticmethod
    def create(settings: Settings) -> Any:
        """Build a model with bounded output, explicit timeout and no hidden retry loop."""
        if settings.llm_provider == "omniroute":
            from langchain_openai import ChatOpenAI

            if not settings.omniroute_api_key or not settings.omniroute_api_key.get_secret_value():
                raise JarvisError("Configure OMNIROUTE_API_KEY com a chave gerada no painel OmniRoute.")
            return ChatOpenAI(model=settings.llm_model, api_key=settings.omniroute_api_key,
                              base_url=settings.omniroute_base_url,
                              max_tokens=settings.llm_max_tokens,
                              timeout=settings.request_timeout, max_retries=0,
                              use_responses_api=False)
        if settings.llm_provider == "openai":
            from langchain_openai import ChatOpenAI

            if not settings.openai_api_key or not settings.openai_api_key.get_secret_value():
                raise JarvisError("Configure OPENAI_API_KEY para o provedor OpenAI.")
            return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key,
                              max_tokens=settings.llm_max_tokens,
                              timeout=settings.request_timeout, max_retries=0)
        if settings.llm_provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            if not settings.google_api_key or not settings.google_api_key.get_secret_value():
                raise JarvisError("Configure GOOGLE_API_KEY para o provedor Gemini.")
            return ChatGoogleGenerativeAI(model=settings.llm_model,
                google_api_key=settings.google_api_key, max_output_tokens=settings.llm_max_tokens,
                timeout=settings.request_timeout, max_retries=0)
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url,
                          num_predict=settings.llm_max_tokens, temperature=0.2,
                          client_kwargs={"timeout": settings.request_timeout})
