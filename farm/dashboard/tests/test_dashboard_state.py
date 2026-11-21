import json
from datetime import timedelta

import pytest

from farm.bot import irrigation
from farm.dashboard import state as dash

from .conftest import LA, NOW, fruit, reading, scan, write_jsonl


def iso(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def test_scan_counts_change_and_labels_only_ripeness(data, settings):
    write_jsonl(data, "scans.jsonl", [
        scan(iso(60), fruit("ripe"), fruit("ripening"), fruit("unripe")),
        scan(iso(5), fruit("ripe"), fruit("ripe"), fruit("ripening"), fruit("mold", crop="scans/x-4.jpg"),
             summary={"mold": 1}),
    ])
    s = dash.build_state(settings, NOW)["scan"]
    assert s["counts"] == {"ripe": 2, "ripening": 1, "unripe": 0}
    assert s["previous"] == {"ripe": 1, "ripening": 1, "unripe": 1}
    assert s["change"] == {"ripe": 1, "ripening": 0, "unripe": -1}
    assert [f["label"] for f in s["fruits"]] == ["ripe", "ripe", "ripening"]
    text = json.dumps(dash.build_state(settings, NOW))
    assert "mold" not in text and "crop" not in text


def test_scan_details_and_unordered_file(data, settings):
    # The newest scan wins by taken_at, whatever the file order.
    write_jsonl(data, "scans.jsonl", [
        scan(iso(5), fruit("ripe"), model="cnn-v2", source="file"),
        scan(iso(90), fruit("unripe")),
    ])
    s = dash.build_state(settings, NOW)["scan"]
    assert (s["model"], s["source"], s["age_s"], s["clock"]) == ("cnn-v2", "file", 300, "2:55 PM")
    assert s["counts"]["ripe"] == 1 and s["change"]["ripe"] == 1


def test_single_scan_has_no_change_and_bad_boxes_are_not_drawn(data, settings):
    write_jsonl(data, "scans.jsonl", [scan(
        iso(1), fruit("ripe"), {"label": "ripe", "bbox": [1, 2, -3, 4]}, {"label": "ripe", "bbox": "nope"})])
    s = dash.build_state(settings, NOW)["scan"]
    assert s["change"] is None and s["counts"]["ripe"] == 3
    assert [bool(f["bbox"]) for f in s["fruits"]] == [True, False, False]


def test_placeholder_frame_wraps_the_boxes(data, settings):
    write_jsonl(data, "scans.jsonl", [scan(iso(1), fruit("ripe", x=40, y=60, w=80, h=82))])
    assert dash.build_state(settings, NOW)["scan"]["frame"] == {"w": 160, "h": 202}


def test_demo_and_simulated_data_are_labelled(data, settings):
    write_jsonl(data, "scans.jsonl", [scan(iso(1), fruit("ripe"), demo=True)])
    write_jsonl(data, "sensors.jsonl", [reading(iso(1), 40, 22, 50, simulated=True)])
    state = dash.build_state(settings, NOW)
    assert [n["key"] for n in state["notices"]] == ["demo", "simulated"]
    assert state["scan"]["demo"] is True and state["watering"]["simulated"] is True
    assert {e["flag"] for e in state["feed"] if e["kind"] in ("scan", "sensors")} == {"demo", "simulated"}


def test_real_data_has_no_notices(data, settings):
    write_jsonl(data, "scans.jsonl", [scan(iso(1), fruit("ripe"))])
    write_jsonl(data, "sensors.jsonl", [reading(iso(1), 40, 22, 50)])
    assert dash.build_state(settings, NOW)["notices"] == []


def test_sensors_latest_value_sparkline_window_and_staleness(data, settings):
    rows = [reading(iso(m), soil=40 - m / 100, temp=20, hum=None) for m in range(0, 24 * 60, 10)]
    rows.append(reading(iso(30 * 60), soil=99, temp=99))  # older than 24 h: not in the sparkline
    write_jsonl(data, "sensors.jsonl", rows)
    sensors = dash.build_state(settings, NOW)["sensors"]
    soil, temp, hum = sensors["metrics"]
    assert soil["value"] == 40 and soil["stale"] is False and soil["threshold"] == 35
    assert len(soil["series"]) <= dash.SPARK_POINTS and soil["high"] < 99
    assert all(sensors["window"][0] <= t <= sensors["window"][1] for t, _ in soil["series"])
    assert temp["value"] == 20 and temp["low"] == temp["high"] == 20
    assert hum["value"] is None and hum["series"] == []  # an unconnected sensor is never invented


def test_old_reading_is_marked_stale_and_has_no_sparkline(data, settings):
    write_jsonl(data, "sensors.jsonl", [reading(iso(3 * 24 * 60), soil=30)])
    soil = dash.build_state(settings, NOW)["sensors"]["metrics"][0]
    assert soil["value"] == 30 and soil["stale"] is True and soil["series"] == []


def test_watering_uses_the_bot_advice(data, settings):
    write_jsonl(data, "sensors.jsonl", [reading(iso(2), soil=20, temp=22, hum=50)])
    water = dash.build_state(settings, NOW)["watering"]
    expected = irrigation.advise([reading(iso(2), 20, 22, 50)], None, NOW.date(), settings.irrigation, now=NOW)
    assert water["cadence"] == irrigation.WATER_TODAY == expected.cadence
    assert (water["title"], water["tone"], water["next_label"]) == ("Water today", "now", "Today")
    assert water["reason"] == expected.reason


def test_watering_cadence_title_and_next_day(data, settings):
    rows = [reading(iso(m), soil=60, temp=15 + 10 * (m % 600 > 300), hum=50) for m in range(0, 24 * 60, 30)]
    write_jsonl(data, "sensors.jsonl", rows)
    water = dash.build_state(settings, NOW)["watering"]
    assert water["cadence"] in irrigation.INTERVAL_DAYS or water["cadence"] == irrigation.HOLD_OFF
    assert water["title"] in (f"Water {water['cadence']}", "Hold off on watering")
    assert water["next_due"] is None or water["next_label"]


def test_cached_forecast_is_used_without_the_network(data, monkeypatch):
    from farm.bot import weather
    from farm.dashboard.settings import Settings

    monkeypatch.setattr(weather, "fetch_open_meteo", lambda *a: pytest.fail("the dashboard must not fetch"))
    cfg = Settings(irrigation.IrrigationConfig(latitude=34.0, longitude=-118.0), LA)
    days = [(NOW.date() + timedelta(days=i)).isoformat() for i in range(7)]
    payload = {"daily": {"time": days, "et0_fao_evapotranspiration": [6.0] * 7, "precipitation_sum": [0.0] * 7}}
    (data / "weather_cache.json").write_text(json.dumps(
        {"fetched_on": NOW.date().isoformat(), "location": [34.0, -118.0], "payload": payload}), encoding="utf-8")
    write_jsonl(data, "sensors.jsonl", [reading(iso(2), soil=60, temp=22, hum=50)])
    before = sorted(p.name for p in data.iterdir())
    water = dash.build_state(cfg, NOW)["watering"]
    assert water["cadence"] == irrigation.TWICE_WEEKLY
    assert sorted(p.name for p in data.iterdir()) == before  # read-only: nothing written
    (data / "weather_cache.json").unlink()
    assert dash.build_state(cfg, NOW)["watering"]["cadence"] != irrigation.TWICE_WEEKLY  # no fetch either


def test_feed_has_scans_ready_picked_watered_and_sensors_newest_first(data, settings):
    write_jsonl(data, "scans.jsonl", [
        scan(iso(120), fruit("ripe")),
        scan(iso(30), fruit("ripe"), fruit("ripe"), fruit("ripe")),
    ])
    write_jsonl(data, "sensors.jsonl", [reading(iso(1), soil=41, temp=22.5, hum=55)])
    write_jsonl(data, "harvest.jsonl", [
        {"taken_at": iso(20), "chat_id": 1, "kind": "picked", "count": 2, "text": "picked 2"},
        {"taken_at": iso(10), "chat_id": 1, "kind": "watered", "count": 1, "text": "watered"},
        {"taken_at": iso(9), "chat_id": 1, "kind": "removed", "count": 1, "text": "removed the moldy one"},
    ])
    feed = dash.build_state(settings, NOW)["feed"]
    assert [e["kind"] for e in feed] == ["sensors", "watered", "picked", "ready", "scan", "scan"]
    assert feed[0]["text"] == "Soil 41%, 22.5 °C, 55% humidity"
    assert feed[2]["text"] == "2 oranges picked"
    assert feed[3]["text"] == "2 more oranges ready to pick, 3 in all"
    assert [e["t"] for e in feed] == sorted((e["t"] for e in feed), reverse=True)


def test_undone_harvest_entries_are_not_listed(data, settings):
    write_jsonl(data, "harvest.jsonl", [
        {"taken_at": iso(20), "chat_id": 1, "kind": "picked", "count": 4, "text": "picked 4"},
        {"taken_at": iso(19), "chat_id": 1, "undo": True},
        {"taken_at": iso(18), "chat_id": None, "kind": "picked", "count": 1, "text": "picked 1", "demo": True},
    ])
    feed = dash.build_state(settings, NOW)["feed"]
    assert [(e["text"], e["flag"]) for e in feed] == [("1 orange picked", "demo")]


def test_corrupt_lines_and_odd_records_are_skipped(data, settings):
    write_jsonl(data, "scans.jsonl", ["{not json", "[1, 2]", json.dumps({"taken_at": "yesterday"}),
                                      json.dumps(scan(iso(1), fruit("ripe"), "x", {"label": None}))])
    write_jsonl(data, "sensors.jsonl", ["", "garbage", json.dumps(reading(iso(1), soil=True, temp=21))])
    state = dash.build_state(settings, NOW)
    assert state["scan"]["counts"]["ripe"] == 1
    soil, temp, _ = state["sensors"]["metrics"]
    assert soil["value"] is None and temp["value"] == 21
