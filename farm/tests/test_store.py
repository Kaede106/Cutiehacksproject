from datetime import datetime

import pytest

from farm.common import store


def test_read_skips_non_objects_and_replaces_invalid_utf8(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    path = tmp_path / store.SENSORS_FILE
    path.write_bytes(b'[]\nnull\n42\n{"partial"\n{"text":"\xff"}\n{"temperature_c":20}\n')
    assert list(store._read(store.SENSORS_FILE)) == [{"text": "\ufffd"}, {"temperature_c": 20}]


@pytest.mark.parametrize("fields", [{}, {"taken_at": []}, {"taken_at": "broken"}])
def test_latest_with_max_age_skips_bad_timestamps(tmp_path, monkeypatch, fields):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    store._append(store.SENSORS_FILE, fields)
    assert store.latest_sensors() is None
    assert store.latest_sensors(max_age=None) == fields


def test_latest_treats_naive_timestamp_as_local_time(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    reading = {"taken_at": datetime.now().isoformat(), "temperature_c": 20}
    store.append_sensors(reading)
    assert store.latest_sensors() == reading
