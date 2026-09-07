"""Safe provider diagnostics: never return raw provider bodies or credentials."""

import asyncio

import httpx

from app.config import Settings


def provider_error(exc: Exception, settings: Settings) -> str:
    """Translate known failures without exposing model prompts in SDK errors."""
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "O modelo excedeu o tempo limite. Teste-o no Ollama e ajuste REQUEST_TIMEOUT se necessário."
    if settings.llm_provider == "omniroute":
        from openai import APIConnectionError, APIStatusError

        if isinstance(exc, APIConnectionError):
            return "OmniRoute inacessível. Inicie o gateway e confira OMNIROUTE_BASE_URL."
        if isinstance(exc, APIStatusError):
            if exc.status_code in (401, 403):
                return "OmniRoute recusou a autenticação. Confira a chave do gateway e suas permissões."
            if exc.status_code == 429:
                return "OmniRoute ou provedor atingiu um limite. Confira cotas e roteamento no gateway."
            return "OmniRoute recusou ou falhou na resposta. Confira o modelo/combo, suporte a ferramentas e conexões no gateway."
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
    if settings.llm_provider == "omniroute":
        result.update(await inspect_omniroute(settings))
        return result
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


async def inspect_omniroute(settings: Settings) -> dict[str, object]:
    """Read the gateway catalog; never proxy provider-management or secret endpoints."""
    if not settings.omniroute_api_key:
        return {"status": "unauthorized", "message": "Configure OMNIROUTE_API_KEY no .env.", "models": []}
    try:
        async with asyncio.timeout(6):
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(settings.omniroute_base_url + "/models",
                    headers={"Authorization": "Bearer " + settings.omniroute_api_key.get_secret_value()})
                response.raise_for_status()
                models = [item["id"] for item in response.json().get("data", [])
                          if isinstance(item, dict) and isinstance(item.get("id"), str)]
        return {"status": "available", "models": models[:500],
                "message": "Catálogo OmniRoute acessível. Disponibilidade, cotas e ferramentas dependem do modelo/combo escolhido."}
    except httpx.HTTPStatusError as exc:
        return {"status": "unauthorized" if exc.response.status_code in (401, 403) else "unavailable",
                "models": [], "message": "OmniRoute recusou a consulta. Confira chave, permissões e URL no .env."}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
        return {"status": "unavailable", "models": [], "message": "OmniRoute inacessível. Inicie o gateway e confira a URL no .env."}
