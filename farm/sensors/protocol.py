"""CutieFarm sensor line protocol: parsing and soil calibration.

One line per reading, `KEY=value` pairs separated by `;`, for example
`SOIL=612;T=22.4;H=55;W=3.2`. The full rules are in farm/sensors/README.md.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("farm.sensors")

# Known keys: (meaning, lowest plausible value, highest plausible value).
# SOIL is raw ADC counts; the others are already calibrated by the board.
KEYS: dict[str, tuple[str, float, float]] = {
    "SOIL": ("raw ADC counts", 0, 65535),
    "T": ("temperature, deg C", -40, 85),
    "H": ("relative humidity, %", 0, 100),
    "W": ("wind speed, m/s", 0, 75),
}
NULL_VALUES = {"nan", "null", "none", ""}
MAX_LINE = 200

# Record fields from farm/CONTRACT.md, in order.
FIELDS = ("soil_moisture_pct", "temperature_c", "humidity_pct", "wind_ms")

# Rough defaults, roughly a capacitive v1.2 probe on a 5 V Uno. Run `calibrate`.
DEFAULT_SOIL_DRY = 600
DEFAULT_SOIL_WET = 280


class MalformedLine(ValueError):
    """A line that does not follow the protocol. The bridge logs and skips it."""


def parse_line(line: str) -> dict[str, float | None] | None:
    """Parse one protocol line.

    Returns None for blank lines and `#` comments. Otherwise returns a dict with
    every known key (SOIL, T, H, W); keys the line does not mention are None.
    Raises MalformedLine for anything that is not a valid reading.
    """
    text = line.strip().strip("\x00")
    if not text or text.startswith("#"):
        return None
    if len(text) > MAX_LINE:
        raise MalformedLine(f"line longer than {MAX_LINE} characters")
    if not text.isascii() or not text.isprintable():
        raise MalformedLine("non-printable characters (wrong baud rate?)")

    values: dict[str, float | None] = dict.fromkeys(KEYS)
    seen: set[str] = set()
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue  # a trailing or doubled ';'
        key, sep, value = part.partition("=")
        key, value = key.strip().upper(), value.strip()
        if not sep or not key or not key.replace("_", "").isalnum():
            raise MalformedLine(f"not KEY=value: {part!r}")
        if key not in KEYS:
            log.debug("ignoring unknown key %s", key)
            continue
        if key in seen:
            raise MalformedLine(f"duplicate key {key}")
        seen.add(key)
        if value.lower() in NULL_VALUES:
            continue  # the board says this sensor has no reading right now
        try:
            number = float(value)
        except ValueError:
            raise MalformedLine(f"{key} is not a number: {value!r}") from None
        if not math.isfinite(number):
            raise MalformedLine(f"{key} is not finite: {value!r}")
        _, low, high = KEYS[key]
        if not low <= number <= high:
            log.warning("%s=%s is outside %s..%s; storing null for it", key, value, low, high)
            continue
        values[key] = number
    if not seen:
        raise MalformedLine("no known keys")
    return values


@dataclass(frozen=True)
class SoilCalibration:
    """Maps raw soil ADC counts to 0..100 % using a dry and a wet reading.

    Works whichever way the probe goes (most read lower when wetter).
    """

    dry: float = DEFAULT_SOIL_DRY
    wet: float = DEFAULT_SOIL_WET

    def __post_init__(self) -> None:
        if self.dry == self.wet:
            raise ValueError("soil dry and wet calibration values must differ")

    def percent(self, raw: float | None) -> float | None:
        if raw is None:
            return None
        pct = (self.dry - raw) / (self.dry - self.wet) * 100.0
        return round(min(100.0, max(0.0, pct)), 1)

    def raw_for(self, pct: float) -> int:
        """Inverse of percent(), used by the simulator."""
        return round(self.dry - pct / 100.0 * (self.dry - self.wet))


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def to_record(values: dict[str, float | None], raw: str, soil: SoilCalibration) -> dict[str, Any]:
    """Build a sensors.jsonl record (without taken_at) from parsed values."""
    return {
        "soil_moisture_pct": soil.percent(values.get("SOIL")),
        "temperature_c": _round(values.get("T")),
        "humidity_pct": _round(values.get("H")),
        "wind_ms": _round(values.get("W")),
        "raw": raw,
    }
