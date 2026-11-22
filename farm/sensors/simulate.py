"""Simulated sensor readings for demos without the board. Every record says so."""
from __future__ import annotations

import logging
import math
import random
import time
from datetime import datetime
from typing import Any, Callable

from farm.common import store
from farm.sensors.protocol import SoilCalibration, parse_line, to_record

log = logging.getLogger("farm.sensors")


class Simulator:
    """Slowly drying soil with an occasional watering, a daily temperature curve,
    humidity that falls as it warms, and light gusty wind."""

    def __init__(self, soil: SoilCalibration, rng: random.Random | None = None):
        self.soil = soil
        self.rng = rng or random.Random()
        self.moisture = self.rng.uniform(40, 55)

    def line(self, when: datetime) -> str:
        r = self.rng
        self.moisture -= r.uniform(0.02, 0.15)
        if self.moisture < 30:
            self.moisture = r.uniform(55, 62)  # someone watered
        hour = when.hour + when.minute / 60
        temp = 20 + 4 * math.sin((hour - 9) / 24 * 2 * math.pi) + r.gauss(0, 0.3)
        humidity = min(95.0, max(20.0, 70 - (temp - 20) * 3 + r.gauss(0, 2)))
        wind = max(0.0, r.gauss(2.0, 1.0))
        soil_raw = self.soil.raw_for(self.moisture + r.gauss(0, 0.5))
        return f"SOIL={soil_raw};T={temp:.1f};H={humidity:.0f};W={wind:.1f}"

    def water(self, seconds: int) -> None:
        """A simulated watering wets the simulated soil, about 3 points a second."""
        self.moisture = min(75.0, self.moisture + 3.0 * seconds)

    def record(self, when: datetime | None = None) -> dict[str, Any]:
        when = when or datetime.now().astimezone()
        raw = self.line(when)
        record = to_record(parse_line(raw), raw, self.soil)  # same path as real lines
        record["taken_at"] = when.isoformat(timespec="seconds")
        record["simulated"] = True
        return record


def simulate(every: float, soil: SoilCalibration, *, count: int | None = None,
             seed: int | None = None,
             write: Callable[[dict[str, Any]], None] = store.append_sensors,
             sleep: Callable[[float], None] = time.sleep,
             water: Any = None) -> int:
    """Write simulated readings every `every` seconds; `count` of them, or forever.

    `water` is an optional farm.irrigation_control.WaterQueue. Its commands are
    checked every second, "run" on the simulated soil and marked "simulated": true."""
    sim = Simulator(soil, random.Random(seed))
    if water is not None:
        water.on_water = sim.water
    written = 0
    log.warning("SIMULATED readings into %s (marked \"simulated\": true)", store.data_dir())
    while count is None or written < count:
        record = sim.record()
        write(record)
        written += 1
        log.info("wrote SIMULATED %s", record["raw"])
        if count is None or written < count:
            _wait(every, sleep, water)
    return written


def _wait(seconds: float, sleep: Callable[[float], None], water: Any) -> None:
    if water is None:
        sleep(seconds)
        return
    left = seconds
    while left > 0:
        water.poll_simulated()
        step = min(1.0, left)
        sleep(step)
        left -= step
