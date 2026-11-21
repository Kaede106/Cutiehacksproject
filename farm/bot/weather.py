"""Open-Meteo daily forecast (ET0 and rain), cached once a day in the data folder.

Only used when FARM_LAT and FARM_LON are set. The coordinates are rounded to two
decimals (about 1 km) before they leave the laptop. Open-Meteo is free and needs
no key. Any network or format problem returns None (or yesterday's cache), so the
advice falls back to the sensor estimate instead of failing.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .irrigation import Weather, WeatherDay, _number

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_FILE = "weather_cache.json"
CACHE_MAX_DAYS = 3  # how old a cached forecast may be when Open-Meteo cannot be reached

log = logging.getLogger(__name__)


def parse_open_meteo(payload: Any, source: str = "Open-Meteo forecast") -> Weather:
    daily = payload["daily"]
    days, et0s = daily["time"], daily["et0_fao_evapotranspiration"]
    rains = daily.get("precipitation_sum") or [None] * len(days)
    out = []
    for d, e, r in zip(days, et0s, rains):
        out.append(WeatherDay(date.fromisoformat(d), _number(e), _number(r)))
    if not out:
        raise ValueError("forecast has no days")
    return Weather(tuple(out), source)


def fetch_open_meteo(lat: float, lon: float, timezone: str) -> Any:
    import httpx

    response = httpx.get(OPEN_METEO_URL, timeout=10, params={
        "latitude": round(lat, 2), "longitude": round(lon, 2),
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "timezone": timezone, "forecast_days": 7,
    })
    response.raise_for_status()
    return response.json()


def get_weather(lat: float | None, lon: float | None, timezone: str, today: date, data_dir: Path,
                fetch: Callable[[float, float, str], Any] = fetch_open_meteo) -> Weather | None:
    if lat is None or lon is None:
        return None
    key = [round(lat, 2), round(lon, 2)]
    cache = _read_cache(data_dir / CACHE_FILE)
    if cache and cache.get("location") == key and cache.get("fetched_on") == today.isoformat():
        try:
            return parse_open_meteo(cache["payload"])
        except (KeyError, TypeError, ValueError):
            pass
    try:
        payload = fetch(lat, lon, timezone)
        weather = parse_open_meteo(payload)
    except Exception as exc:  # network, HTTP status, bad JSON: never break the message
        log.warning("Open-Meteo forecast unavailable (%s). Using the cache or the sensor estimate.",
                    type(exc).__name__)
        return _stale(cache, key, today)
    _write_cache(data_dir / CACHE_FILE, {"fetched_on": today.isoformat(), "location": key, "payload": payload})
    return weather


def _stale(cache: dict | None, key: list[float], today: date) -> Weather | None:
    if not cache or cache.get("location") != key:
        return None
    try:
        fetched = date.fromisoformat(cache["fetched_on"])
        if today - fetched > timedelta(days=CACHE_MAX_DAYS):
            return None
        return parse_open_meteo(cache["payload"], f"Open-Meteo forecast from {fetched:%b} {fetched.day} (offline)")
    except (KeyError, TypeError, ValueError):
        return None


def _read_cache(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, data: dict) -> None:
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        log.warning("Could not write %s", path.name)
