"""Weather service — Open-Meteo API (free, no key required)."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class DayWeather:
    """Weather summary for a single day."""
    date: str
    temp_max: float
    temp_min: float
    precipitation_mm: float
    weather_code: int
    description: str
    is_rainy: bool


# WMO weather codes → human descriptions
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

_RAINY_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}


async def get_weather_forecast(lat: float, lng: float, days: int = 7) -> list[DayWeather]:
    """Fetch weather forecast from Open-Meteo. Returns up to 16 days."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
        "forecast_days": min(days, 16),
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        result = []
        for i, date in enumerate(dates):
            code = daily["weather_code"][i]
            result.append(DayWeather(
                date=date,
                temp_max=daily["temperature_2m_max"][i],
                temp_min=daily["temperature_2m_min"][i],
                precipitation_mm=daily["precipitation_sum"][i],
                weather_code=code,
                description=_WMO_CODES.get(code, "Unknown"),
                is_rainy=code in _RAINY_CODES,
            ))
        return result
    except Exception as e:
        logger.warning(f"[Weather] Open-Meteo error: {e}")
        return []
