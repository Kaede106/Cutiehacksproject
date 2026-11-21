import random

from farm.common import store
from farm.sensors.protocol import SoilCalibration, parse_line
from farm.sensors.simulate import Simulator, simulate


def test_simulated_records_are_flagged_and_plausible():
    sim = Simulator(SoilCalibration(600, 280), random.Random(1))
    for _ in range(500):
        r = sim.record()
        assert r["simulated"] is True
        assert 0 <= r["soil_moisture_pct"] <= 100
        assert 10 <= r["temperature_c"] <= 30
        assert 20 <= r["humidity_pct"] <= 95
        assert 0 <= r["wind_ms"] < 10
        assert parse_line(r["raw"]) is not None


def test_simulate_writes_through_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    sleeps = []
    assert simulate(10.0, SoilCalibration(), count=3, seed=7, sleep=sleeps.append) == 3
    assert sleeps == [10.0, 10.0]
    lines = (tmp_path / store.SENSORS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    latest = store.latest_sensors()
    assert latest["simulated"] is True
    assert set(latest) == {"taken_at", "soil_moisture_pct", "temperature_c", "humidity_pct",
                           "wind_ms", "raw", "simulated"}
