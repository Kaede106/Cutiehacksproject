"""Shared on-disk store for CutieFarm's laptop-side programs.

The vision runner, the sensor bridge and the Telegram bot do not talk to each
other directly. They share append-only JSON Lines files in one data folder,
described in farm/CONTRACT.md. Use only these helpers to read and write them.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

LABELS = ("unripe", "ripening", "ripe", "mold")
CONFIDENCE = ("high", "medium", "low")

SCANS_FILE = "scans.jsonl"
SENSORS_FILE = "sensors.jsonl"


def data_dir() -> Path:
    """Data folder: $CUTIEFARM_DATA, or farm/data next to this package."""
    env = os.environ.get("CUTIEFARM_DATA")
    path = Path(env) if env else Path(__file__).resolve().parent.parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    """Current local time as ISO 8601 with its UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _append(name: str, record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    # One write call per record, so a reader never sees half a line from us.
    with open(data_dir() / name, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def _read(name: str) -> Iterator[dict[str, Any]]:
    path = data_dir() / name
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # a line still being written, or a corrupt one


def _latest(name: str, max_age: timedelta | None) -> dict[str, Any] | None:
    latest = None
    for record in _read(name):
        latest = record
    if latest is None or max_age is None:
        return latest
    taken = datetime.fromisoformat(latest["taken_at"])
    if datetime.now(timezone.utc) - taken > max_age:
        return None
    return latest


def append_scan(scan: dict[str, Any]) -> None:
    """Append one scan record (see CONTRACT.md). Fills taken_at if missing."""
    scan.setdefault("taken_at", now_iso())
    for fruit in scan.get("fruits", []):
        if fruit.get("label") not in LABELS:
            raise ValueError(f"unknown label: {fruit.get('label')!r}")
    scan["summary"] = {label: sum(1 for f in scan.get("fruits", []) if f["label"] == label) for label in LABELS}
    _append(SCANS_FILE, scan)


def latest_scan(max_age: timedelta | None = timedelta(hours=24)) -> dict[str, Any] | None:
    """Most recent scan, or None if there is none newer than max_age."""
    return _latest(SCANS_FILE, max_age)


def append_sensors(reading: dict[str, Any]) -> None:
    """Append one sensor reading (see CONTRACT.md). Fills taken_at if missing."""
    reading.setdefault("taken_at", now_iso())
    _append(SENSORS_FILE, reading)


def latest_sensors(max_age: timedelta | None = timedelta(hours=1)) -> dict[str, Any] | None:
    """Most recent sensor reading, or None if there is none newer than max_age."""
    return _latest(SENSORS_FILE, max_age)


def resolve(relative: str) -> Path:
    """Turn a path stored in a record (relative to the data folder) into a real path."""
    return data_dir() / relative
