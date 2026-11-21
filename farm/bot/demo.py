"""Seed a data folder with clearly marked demo data, so the bot can be shown before the camera
and the sensor board are connected.

Scans and harvest entries have "demo": true, and sensor readings have "simulated": true.
Point CUTIEFARM_DATA at a separate folder (for example
farm/data-demo) so demo data never mixes with real scans.
"""
from __future__ import annotations

import math
import struct
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from farm.bot import fixtures, harvest
from farm.common import store


def _png(path: Path, size: int = 256) -> None:
    """Draw a small picture of an orange with blue-green mold spots, with no imaging library."""
    cx = cy = size / 2
    r = size * 0.36
    spots = [(0.58, 0.55, 0.12), (0.44, 0.63, 0.07), (0.62, 0.40, 0.06)]
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type: none
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            if d > r:
                rgb = (23, 70, 42)  # leaf-green background
            else:
                shade = 1 - 0.45 * (d / r) ** 2
                light = max(0.0, 1 - math.hypot(x - cx * 0.75, y - cy * 0.7) / (r * 0.9)) * 0.25
                rgb = tuple(min(255, int(c * shade + 255 * light)) for c in (238, 132, 40))
                for sx, sy, sr in spots:
                    ds = math.hypot(x - size * sx, y - size * sy)
                    if ds < size * sr * 1.5:  # white fuzz around each spot
                        rgb = tuple(int(a * 0.4 + 235 * 0.6) for a in rgb)
                    if ds < size * sr:
                        rgb = (78, 150, 140)
            row.extend(rgb)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def _seed_week(now: datetime) -> None:
    # Counts in the six scans leading up to the usual mold fixture.
    history = [(0, 2, 9, 0), (0, 3, 8, 0), (1, 4, 6, 1),
               (1, 5, 4, 0), (2, 5, 3, 0), (3, 5, 2, 1)]
    labels = ("ripe", "ripening", "unripe", "mold")
    for days_ago, counts in zip(range(6, 0, -1), history):
        fruits = [label for label, count in zip(labels, counts) for _ in range(count)]
        scan = fixtures._scan(now - timedelta(days=days_ago), fruits)
        for fruit in scan["fruits"]:
            fruit["crop"] = None
        store.append_scan(dict(scan, image=None, demo=True))

    for days_ago, kind, count, text in (
        (5, "watered", 1, "I watered"),
        (3, "removed", 1, "removed the moldy one"),
        (2, "picked", 1, "picked 1"),
        (1, "watered", 1, "I watered"),
    ):
        taken_at = (now - timedelta(days=days_ago)).isoformat(timespec="seconds")
        harvest.append_entry(None, kind, count, text, taken_at=taken_at, demo=True)


def seed(now: datetime | None = None, *, week: bool = False) -> Path:
    """Write one demo scan (3 ready, 5 ripening, 1 possible mold) and 3 days of simulated
    hot, dry sensor readings. With week=True, add scan history and example harvest entries."""
    now = now or datetime.now().astimezone()
    folder = store.data_dir()

    for reading in fixtures.hot_dry(now).history:
        reading = dict(reading, simulated=True)
        store.append_sensors(reading)

    if week:
        _seed_week(now)
    scan = dict(fixtures.mold(now).scan, demo=True)
    for fruit in scan["fruits"]:
        if fruit.get("crop"):
            fruit["crop"] = fruit["crop"].replace(".jpg", ".png")
            _png(folder / fruit["crop"])
    scan["image"] = None
    store.append_scan(scan)
    return folder
