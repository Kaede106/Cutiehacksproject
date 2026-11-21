"""Seed a data folder with clearly marked demo data, so the bot can be shown before the camera
and the sensor board are connected.

Scans and harvest entries have "demo": true, and sensor readings have "simulated": true.
Point CUTIEFARM_DATA at a separate folder (for example
farm/data-demo) so demo data never mixes with real scans.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from farm.bot import fixtures, harvest
from farm.common import store


def _seed_week(now: datetime) -> None:
    # Counts in the six scans leading up to the latest demo scan.
    history = [(0, 2, 9), (0, 3, 8), (1, 4, 6),
               (1, 5, 4), (2, 5, 3), (2, 6, 2)]
    labels = ("ripe", "ripening", "unripe")
    for days_ago, counts in zip(range(6, 0, -1), history):
        fruits = [label for label, count in zip(labels, counts) for _ in range(count)]
        scan = fixtures._scan(now - timedelta(days=days_ago), fruits)
        store.append_scan(dict(scan, image=None, demo=True))

    for days_ago, kind, count, text in (
        (5, "watered", 1, "I watered"),
        (2, "picked", 1, "picked 1"),
        (1, "watered", 1, "I watered"),
    ):
        taken_at = (now - timedelta(days=days_ago)).isoformat(timespec="seconds")
        harvest.append_entry(None, kind, count, text, taken_at=taken_at, demo=True)


def seed(now: datetime | None = None, *, week: bool = False) -> Path:
    """Write one demo scan (3 ready, 5 ripening) and 3 days of simulated
    hot, dry sensor readings. With week=True, add scan history and example harvest entries."""
    now = now or datetime.now().astimezone()
    folder = store.data_dir()

    example = fixtures.pick_and_water(now)
    for reading in example.history:
        store.append_sensors(reading)

    if week:
        _seed_week(now)
    store.append_scan(dict(example.scan, image=None, demo=True))
    return folder
