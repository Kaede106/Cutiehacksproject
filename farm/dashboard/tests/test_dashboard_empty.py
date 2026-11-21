import json

from farm.dashboard import state as dash

from .conftest import NOW, write_jsonl


def test_missing_data_folder_is_reported_and_not_created(tmp_path, monkeypatch, settings):
    missing = tmp_path / "nope"
    monkeypatch.setenv("CUTIEFARM_DATA", str(missing))
    state = dash.build_state(settings, NOW)
    assert state["data_folder"] is False
    assert state["scan"] is None and state["watering"] is None and state["feed"] == []
    assert not any(m["value"] is not None or m["series"] for m in state["sensors"]["metrics"])
    assert not missing.exists()  # a read-only dashboard does not create the folder
    json.dumps(state)


def test_empty_data_folder(data, settings):
    state = dash.build_state(settings, NOW)
    assert state["data_folder"] is True
    assert state["scan"] is None and state["feed"] == [] and state["notices"] == []
    assert state["sensors"]["any"] is False
    assert state["watering"]["cadence"] == "not enough data" and state["watering"]["tone"] == "unknown"
    assert list(data.iterdir()) == []  # nothing written


def test_scan_without_a_photo_or_fruit(data, settings):
    write_jsonl(data, "scans.jsonl", [{"taken_at": "2026-11-21T14:59:00-08:00", "fruits": [], "image": None}])
    scan = dash.build_state(settings, NOW)["scan"]
    assert scan["counts"] == {"ripe": 0, "ripening": 0, "unripe": 0}
    assert scan["image"] is None and scan["model"] is None and scan["frame"] == {"w": 640, "h": 360}


def test_sensors_without_scans(data, settings):
    write_jsonl(data, "sensors.jsonl", [{"taken_at": "2026-11-21T14:59:00-08:00", "soil_moisture_pct": 50}])
    state = dash.build_state(settings, NOW)
    assert state["scan"] is None and state["sensors"]["any"] is True
    assert [e["kind"] for e in state["feed"]] == ["sensors"]
