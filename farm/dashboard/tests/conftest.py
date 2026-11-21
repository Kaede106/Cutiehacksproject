import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from farm.bot.irrigation import IrrigationConfig
from farm.dashboard.settings import Settings

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 21, 15, 0, tzinfo=LA)


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A temp data folder, used as CUTIEFARM_DATA."""
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def settings():
    return Settings(IrrigationConfig(), LA)


def write_jsonl(folder, name, records):
    with open(folder / name, "w", encoding="utf-8") as f:
        for record in records:
            f.write((record if isinstance(record, str) else json.dumps(record)) + "\n")


def fruit(label, x=10, y=20, w=50, h=52, **extra):
    return {"id": 1, "label": label, "confidence": "high", "bbox": [x, y, w, h], **extra}


def scan(taken_at, *fruits, **extra):
    return {"id": taken_at, "taken_at": taken_at, "source": "webcam", "model": "color-heuristic-v1",
            "image": None, "fruits": list(fruits), **extra}


def reading(taken_at, soil=None, temp=None, hum=None, **extra):
    return {"taken_at": taken_at, "soil_moisture_pct": soil, "temperature_c": temp,
            "humidity_pct": hum, "wind_ms": None, **extra}
