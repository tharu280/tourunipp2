from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import requests

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def build_trip_dates(start_date: str, trip_days: int) -> list[str]:
    start = date.fromisoformat(start_date)
    total_days = max(trip_days, 1)
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(total_days)
    ]


def fetch_weather_for_point(
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    timeout: int = 30,
) -> dict[str, Any]:
    return _fetch_weather_cached(
        latitude=round(latitude, 3),
        longitude=round(longitude, 3),
        start_date=start_date,
        end_date=end_date,
        timeout=timeout,
    )


@lru_cache(maxsize=256)
def _fetch_weather_cached(
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    timeout: int = 30,
) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
            ]
        ),
    }
    response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def summarize_daily_weather(payload: dict[str, Any]) -> dict[str, Any]:
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    if not times:
        return {"status": "unavailable"}

    return {
        "status": "ok",
        "dates": times,
        "weather_codes": daily.get("weather_code", []),
        "temperature_max": daily.get("temperature_2m_max", []),
        "temperature_min": daily.get("temperature_2m_min", []),
        "precipitation_sum": daily.get("precipitation_sum", []),
        "precipitation_probability_max": daily.get(
            "precipitation_probability_max",
            [],
        ),
        "wind_speed_max": daily.get("wind_speed_10m_max", []),
    }


def weather_risk_score(forecast: dict[str, Any], *, day_index: int) -> dict[str, Any]:
    if forecast.get("status") != "ok":
        return {
            "score": None,
            "risk_level": "unknown",
            "reasons": ["Forecast unavailable."],
        }

    rain_probs = forecast.get("precipitation_probability_max", [])
    rainfall = forecast.get("precipitation_sum", [])
    wind_speeds = forecast.get("wind_speed_max", [])

    if day_index >= len(rain_probs):
        return {
            "score": None,
            "risk_level": "unknown",
            "reasons": ["No forecast available for this trip day."],
        }

    rain_prob = float(rain_probs[day_index] or 0)
    rain_total = float(rainfall[day_index] or 0)
    wind_speed = float(wind_speeds[day_index] or 0)

    score = 0
    reasons: list[str] = []

    if rain_prob >= 80:
        score += 40
        reasons.append(f"rain probability is very high at {round(rain_prob)}%")
    elif rain_prob >= 60:
        score += 25
        reasons.append(f"rain probability is elevated at {round(rain_prob)}%")
    elif rain_prob >= 40:
        score += 10
        reasons.append(f"some rain risk remains at {round(rain_prob)}%")

    if rain_total >= 20:
        score += 30
        reasons.append(f"heavy rainfall is forecast around {rain_total} mm")
    elif rain_total >= 8:
        score += 15
        reasons.append(f"moderate rainfall is forecast around {rain_total} mm")

    if wind_speed >= 40:
        score += 20
        reasons.append(f"strong winds may reach {round(wind_speed)} km/h")
    elif wind_speed >= 28:
        score += 10
        reasons.append(f"wind may stay noticeable around {round(wind_speed)} km/h")

    if score >= 60:
        risk_level = "high"
    elif score >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "score": score,
        "risk_level": risk_level,
        "reasons": reasons or ["Weather conditions look manageable."],
    }
