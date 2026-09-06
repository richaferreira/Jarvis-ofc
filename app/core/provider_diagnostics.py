"""Safe provider diagnostics: never return raw provider bodies or credentials."""

import asyncio

import httpx

from app.config import Settings


def provider_error(exc: Exception, settings: Settings) -> str:
    """Translate known failures without exposing model prompts in SDK errors."""
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "O modelo excedeu o tempo limite. Teste-o no Ollama e ajuste REQUEST_TIMEOUT se necessário."
    if settings.llm_provider == "ollama":
        from ollama import ResponseError

        if isinstance(exc, ResponseError):
            if exc.status_code == 404:
                return "Ollama retornou 404. Confira LLM_MODEL, execute ollama list e baixe o modelo configurado com ollama pull."
            if exc.status_code == 400:
                return "Ollama rejeitou a solicitação (400). Confira se o modelo suporta ferramentas e atualize o Ollama."
            if exc.status_code and exc.status_code >= 500:
                return "Ollama falhou ao executar o modelo (erro de servidor). Teste ollama run e confira memória RAM/VRAM disponível."
            return "Ollama retornou um erro. Execute ollama run com o modelo do .env para conferir o diagnóstico local."
        if isinstance(exc, (ConnectionError, httpx.ConnectError)):
            return "Não foi possível conectar ao Ollama. Abra o aplicativo e confira OLLAMA_BASE_URL no .env."
    return "Não foi possível concluir a resposta. Verifique a conexão, o provedor e o modelo configurado."


async def inspect_provider(settings: Settings) -> dict[str, object]:
    """Read Ollama inventory only; presence does not prove inference health."""
    result: dict[str, object] = {
        "provider": settings.llm_provider, "model": settings.llm_model,
        "memory_enabled": settings.memory_enabled, "timezone": settings.timezone,
        "max_input_chars": settings.max_input_chars,
        "home_actions": [action.description for action in settings.home_actions.values()],
        "status": "not_checked", "message": "Provedor configurado; inferência ainda não testada.",
    }
    if settings.llm_provider != "ollama":
        return result
    try:
        async with asyncio.timeout(6):
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(settings.ollama_base_url + "/api/tags")
                response.raise_for_status()
                models = [m["name"] for m in response.json().get("models", [])]
        configured = settings.llm_model
        found = configured in models or (":" not in configured and configured + ":latest" in models)
        result.update(status="available" if found else "missing_model", models=models,
                      message="Modelo instalado; inferência ainda não testada." if found else
                      "Modelo não instalado neste Ollama. Execute ollama pull com o nome configurado.")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
        result.update(status="unavailable", message="Não foi possível consultar o Ollama. Confira o serviço e a URL no .env.")
    return result
