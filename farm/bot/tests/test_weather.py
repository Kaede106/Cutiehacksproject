import json
from datetime import date, timedelta

from farm.bot.weather import CACHE_FILE, get_weather, parse_open_meteo

TODAY = date(2026, 11, 21)
PAYLOAD = {"daily": {"time": ["2026-11-21", "2026-11-22"], "et0_fao_evapotranspiration": [2.89, None],
                     "precipitation_sum": [0.0, 1.5]}}


def fetcher(calls, payload=PAYLOAD, fail=False):
    def fetch(lat, lon, tz):
        calls.append((lat, lon, tz))
        if fail:
            raise OSError("offline")
        return payload
    return fetch


def test_parse():
    w = parse_open_meteo(PAYLOAD)
    assert [(d.day, d.et0_mm, d.rain_mm) for d in w.days] == [(TODAY, 2.89, 0.0), (TODAY + timedelta(days=1), None, 1.5)]


def test_parse_ignores_nonfinite_forecast_values():
    payload = {"daily": {**PAYLOAD["daily"], "et0_fao_evapotranspiration": [float("inf"), float("nan")],
                         "precipitation_sum": [float("-inf"), 1.5]}}
    first, second = parse_open_meteo(payload).days
    assert (first.et0_mm, first.rain_mm, second.et0_mm, second.rain_mm) == (None, None, None, 1.5)


def test_no_location_no_request(tmp_path):
    calls = []
    assert get_weather(None, None, "UTC", TODAY, tmp_path, fetcher(calls)) is None
    assert get_weather(34.0, None, "UTC", TODAY, tmp_path, fetcher(calls)) is None
    assert calls == []


def test_fetched_once_a_day(tmp_path):
    calls = []
    assert get_weather(34.0512, -118.2437, "UTC", TODAY, tmp_path, fetcher(calls)) is not None
    assert get_weather(34.0512, -118.2437, "UTC", TODAY, tmp_path, fetcher(calls)) is not None
    assert len(calls) == 1
    assert json.loads((tmp_path / CACHE_FILE).read_text())["location"] == [34.05, -118.24]
    get_weather(34.0512, -118.2437, "UTC", TODAY + timedelta(days=1), tmp_path, fetcher(calls))
    assert len(calls) == 2


def test_network_failure_uses_recent_cache_then_gives_up(tmp_path):
    get_weather(34.0, -118.0, "UTC", TODAY, tmp_path, fetcher([]))
    w = get_weather(34.0, -118.0, "UTC", TODAY + timedelta(days=1), tmp_path, fetcher([], fail=True))
    assert w is not None and "(offline)" in w.source
    assert get_weather(34.0, -118.0, "UTC", TODAY + timedelta(days=5), tmp_path, fetcher([], fail=True)) is None


def test_network_failure_without_cache_or_other_location(tmp_path):
    assert get_weather(34.0, -118.0, "UTC", TODAY, tmp_path, fetcher([], fail=True)) is None
    get_weather(34.0, -118.0, "UTC", TODAY, tmp_path, fetcher([]))
    assert get_weather(40.0, -74.0, "UTC", TODAY, tmp_path, fetcher([], fail=True)) is None


def test_bad_payload_is_a_failure_not_a_crash(tmp_path):
    assert get_weather(34.0, -118.0, "UTC", TODAY, tmp_path, fetcher([], payload={"error": True})) is None
    assert not (tmp_path / CACHE_FILE).exists()
