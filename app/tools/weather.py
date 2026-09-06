"""Open-Meteo geocoding and current weather integration."""

from typing import Any

from app.exceptions import ServiceUnavailable
from app.infrastructure.http_client import HttpClient


class WeatherService:
    """Look up a named city and report the resolved location alongside measurements."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    async def current(self, city: str, country_code: str = "BR") -> dict[str, Any]:
        """Return current weather; report ambiguity rather than guessing a city."""
        places = await self.http.get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": city, "count": 5, "language": "pt", "format": "json", "countryCode": country_code},
        )
        results = places.get("results", [])
        if not results:
            return {"error": "Cidade não encontrada. Informe nome e país."}
        if len(results) > 1:
            return {"clarification_required": True, "locations": [
                {k: p.get(k) for k in ("name", "admin1", "country", "latitude", "longitude")}
                for p in results
            ]}
        place = results[0]
        return await self.coordinates(float(place["latitude"]), float(place["longitude"]), place["name"])

    async def coordinates(self, latitude: float, longitude: float, location: str = "") -> dict[str, Any]:
        """Fetch measurements for exact coordinates in SI units."""
        data = await self.http.get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": latitude, "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        })
        if "current" not in data:
            raise ServiceUnavailable("Dados meteorológicos indisponíveis.")
        return {"location": location, "latitude": latitude, "longitude": longitude,
                "current": data["current"], "units": data.get("current_units", {}),
                "timezone": data.get("timezone"), "source": "https://open-meteo.com/"}
