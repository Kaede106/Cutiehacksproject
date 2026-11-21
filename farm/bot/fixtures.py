"""Made-up records for previews and demos without a camera, a board, a forecast or Telegram.

Each fixture is built relative to `now`, so it always looks like this morning's
data (or, for "stale", like data that is too old). Forecasts in fixtures are
labelled as made up, so a preview never passes them off as Open-Meteo data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from farm.common.store import LABELS

from .irrigation import Weather, WeatherDay


@dataclass(frozen=True)
class Fixture:
    scan: dict[str, Any] | None
    sensors: dict[str, Any] | None = None  # latest reading, as store.latest_sensors returns it
    history: list[dict[str, Any]] = field(default_factory=list)  # sensor readings, oldest first
    weather: Weather | None = None


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _scan(now: datetime, labels: list[str], *, age: timedelta = timedelta(minutes=4),
          model: str = "color-heuristic-v1", confidence: dict[int, str] | None = None) -> dict[str, Any]:
    taken = now - age
    scan_id = f"{taken:%Y%m%dT%H%M%S}-demo"
    fruits = []
    for i, label in enumerate(labels, start=1):
        fruits.append({
            "id": i,
            "label": label,
            "confidence": (confidence or {}).get(i, "high"),
            "bbox": [40 + 90 * (i % 6), 60 + 100 * (i // 6), 80, 82],
        })
    return {
        "id": scan_id,
        "taken_at": _iso(taken),
        "source": "webcam",
        "model": model,
        "image": f"scans/{scan_id}.jpg",
        "fruits": fruits,
        "summary": {k: labels.count(k) for k in LABELS},
    }


def _sensors(now: datetime, *, simulated: bool, wind: float | None = 3.2) -> dict[str, Any]:
    reading = {
        "taken_at": _iso(now - timedelta(minutes=6)),
        "soil_moisture_pct": 41.0,
        "temperature_c": 22.4,
        "humidity_pct": 55.0,
        "wind_ms": wind,
        "raw": "SOIL=612;T=22.4;H=55;W=" + ("3.2" if wind is not None else ""),
    }
    if simulated:
        reading["simulated"] = True
    return reading


def _history(now: datetime, *, days: float, soil_now: float | None, soil_per_day: float, t_low: float,
             t_high: float, humidity: float, wind: float | None, every: timedelta = timedelta(hours=2),
             simulated: bool = True) -> list[dict[str, Any]]:
    """Readings every `every` until 6 minutes ago; temperature lowest at 5 AM, highest at 3 PM."""
    end = now - timedelta(minutes=6)
    steps = int(timedelta(days=days) / every)
    out = []
    for i in range(steps, -1, -1):
        t = end - i * every
        ago_days = (end - t) / timedelta(days=1)
        hour = t.hour + t.minute / 60
        temp = (t_low + t_high) / 2 + (t_high - t_low) / 2 * math.cos(2 * math.pi * (hour - 15) / 24)
        reading = {
            "taken_at": _iso(t),
            "soil_moisture_pct": None if soil_now is None else round(soil_now + soil_per_day * ago_days, 1),
            "temperature_c": round(temp, 1),
            "humidity_pct": humidity,
            "wind_ms": wind,
        }
        if simulated:
            reading["simulated"] = True
        out.append(reading)
    return out


def _forecast(now: datetime, et0: list[float], rain: list[float]) -> Weather:
    today = now.date()
    days = tuple(WeatherDay(today + timedelta(days=i), e, r) for i, (e, r) in enumerate(zip(et0, rain)))
    return Weather(days, "Made-up forecast (fixture)")


def _with(history: list[dict[str, Any]], scan: dict[str, Any], weather: Weather | None = None) -> Fixture:
    return Fixture(scan, history[-1] if history else None, history, weather)


# --- oranges -------------------------------------------------------------------


def ripe_heavy(now: datetime) -> Fixture:
    return Fixture(_scan(now, ["ripe"] * 6 + ["ripening"] * 2 + ["unripe"]))


def pick_and_water(now: datetime) -> Fixture:
    history = hot_dry(now).history
    return _with(history, _scan(now, ["ripe"] * 3 + ["ripening"] * 5))


def empty(now: datetime) -> Fixture:
    return Fixture(_scan(now, []))


def stale(now: datetime) -> Fixture:
    return Fixture(_scan(now, ["ripe"] * 2 + ["ripening"], age=timedelta(days=2, hours=1)))


def unripe(now: datetime) -> Fixture:
    return Fixture(_scan(now, ["unripe"] * 7))


def sensors_simulated(now: datetime) -> Fixture:
    reading = _sensors(now, simulated=True, wind=None)  # wind not connected: skipped
    return Fixture(_scan(now, ["ripe"] * 2 + ["ripening"] * 4 + ["unripe"] * 3), reading, [reading])


# --- watering --------------------------------------------------------------------


def _grove(now: datetime) -> dict[str, Any]:
    return _scan(now, ["ripe"] * 2 + ["ripening"] * 4 + ["unripe"] * 2)


def hot_dry(now: datetime) -> Fixture:
    history = _history(now, days=3, soil_now=47.0, soil_per_day=4.0, t_low=21, t_high=36, humidity=22, wind=4.5)
    weather = _forecast(now, [6.8, 7.1, 6.9, 7.3, 7.0, 6.6, 6.9], [0] * 7)
    return _with(history, _grove(now), weather)


def cool_wet(now: datetime) -> Fixture:
    history = _history(now, days=2, soil_now=63.0, soil_per_day=-1.0, t_low=8, t_high=15, humidity=85, wind=2.0)
    weather = _forecast(now, [1.2, 0.9, 1.0, 1.4, 1.3, 1.1, 1.2], [6.0, 12.5, 4.0, 0, 0, 2.0, 0])
    return _with(history, _grove(now), weather)


def soil_low(now: datetime) -> Fixture:
    history = _history(now, days=2, soil_now=28.0, soil_per_day=3.0, t_low=14, t_high=27, humidity=45, wind=2.5)
    weather = _forecast(now, [3.6, 3.8, 3.5, 3.9, 4.0, 3.7, 3.6], [0] * 7)
    return _with(history, _grove(now), weather)


def sensors_only(now: datetime) -> Fixture:
    # No FARM_LAT/FARM_LON: ET0 comes from the sensor temperatures (Hargreaves).
    history = _history(now, days=3, soil_now=44.0, soil_per_day=1.5, t_low=11, t_high=25, humidity=50, wind=3.0)
    return _with(history, _grove(now))


def no_data(now: datetime) -> Fixture:
    return Fixture(_grove(now))


FIXTURES: dict[str, Callable[[datetime], Fixture]] = {
    "ripe-heavy": ripe_heavy,
    "pick-and-water": pick_and_water,
    "empty": empty,
    "stale": stale,
    "unripe": unripe,
    "sensors-simulated": sensors_simulated,
    "hot-dry": hot_dry,
    "cool-wet": cool_wet,
    "soil-low": soil_low,
    "sensors-only": sensors_only,
    "no-data": no_data,
}
