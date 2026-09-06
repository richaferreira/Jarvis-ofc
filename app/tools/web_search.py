"""DuckDuckGo search isolated from the asynchronous event loop."""

from typing import Any

from app.exceptions import ServiceUnavailable
from app.infrastructure.worker import BlockingWorker


class WebSearch:
    """Bound search work and normalize snippets as untrusted external content."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.worker = BlockingWorker("search")

    def _search(self, query: str) -> list[dict[str, Any]]:
        from ddgs import DDGS

        results = DDGS(timeout=int(self.timeout)).text(query, max_results=5, backend="duckduckgo")
        return [{"title": str(r.get("title", ""))[:250],
                 "url": str(r.get("href", ""))[:1000],
                 "snippet": str(r.get("body", ""))[:1200]} for r in results][:5]

    async def search(self, query: str) -> dict[str, Any]:
        """Fetch up to five results; do not misrepresent failures as empty searches."""
        try:
            return {"untrusted_content": True, "results": await self.worker.run(self._search, query)}
        except Exception as exc:
            raise ServiceUnavailable("Pesquisa indisponível; tente novamente mais tarde.") from exc

    async def aclose(self) -> None:
        """Drain native search work."""
        await self.worker.aclose()
