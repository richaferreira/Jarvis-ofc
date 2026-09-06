"""Shared asynchronous HTTP access with safe GET retries and bounded responses."""

import asyncio
from typing import Any

import httpx

from app.exceptions import ServiceUnavailable


class HttpClient:
    """Reuse connections and never retry POST requests implicitly."""

    def __init__(self, timeout: float, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            transport=transport,
        )

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Retry transient GET failures once; enforce a response-size ceiling."""
        for attempt in range(2):
            try:
                async with self.client.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise ServiceUnavailable("Resposta externa excedeu o limite.")
                    import json

                    return json.loads(body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 1:
                    raise ServiceUnavailable("Serviço externo indisponível.") from exc
                await asyncio.sleep(0.25)
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise ServiceUnavailable("O serviço externo retornou uma resposta inválida.") from exc
        raise ServiceUnavailable("Serviço externo indisponível.")

    async def aclose(self) -> None:
        """Release all pooled connections."""
        await self.client.aclose()
