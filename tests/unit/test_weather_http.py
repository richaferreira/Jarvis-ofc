import httpx

from app.infrastructure.http_client import HttpClient
from app.tools.weather import WeatherService


async def test_weather_ambiguity_does_not_guess_coordinates():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [
            {"name": "Santa Maria", "admin1": "RS", "latitude": -29, "longitude": -53},
            {"name": "Santa Maria", "admin1": "RN", "latitude": -5, "longitude": -35}]})

    http = HttpClient(2, httpx.MockTransport(handle))
    result = await WeatherService(http).current("Santa Maria")
    assert result["clarification_required"] is True
    assert len(calls) == 1
    await http.aclose()


async def test_http_get_retries_transient_error_once():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json={"ok": True})

    http = HttpClient(2, httpx.MockTransport(handle))
    assert await http.get_json("https://example.test") == {"ok": True}
    assert len(calls) == 2
    await http.aclose()
