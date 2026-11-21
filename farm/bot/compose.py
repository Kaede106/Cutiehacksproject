"""Compose the grower's message from the latest scan and sensor reading.

`compose` is a pure function: it takes records as read through farm/common/store.py
(see farm/CONTRACT.md) and the current time, and returns the text (Telegram HTML)
and the photos to attach. It never touches the disk or the network, so it is easy
to test and to preview without Telegram.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from .irrigation import Advice, advice_line

LABELS = ("unripe", "ripening", "ripe", "mold")

SCAN_MAX_AGE = timedelta(hours=24)
SENSOR_MAX_AGE = timedelta(hours=1)  # same default as store.latest_sensors
MAX_PHOTOS = 3

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Photo:
    path: str  # relative to the data folder, as stored in the scan record
    caption: str  # Telegram HTML


@dataclass(frozen=True)
class Message:
    text: str  # Telegram HTML (parse_mode="HTML")
    photos: tuple[Photo, ...] = ()


def compose(
    scan: Mapping[str, Any] | None,
    sensors: Mapping[str, Any] | None,
    now: datetime,
    *,
    photo_ok: Callable[[str], bool] | None = None,
    scan_command: str | None = None,
    irrigation: Advice | None = None,
) -> Message:
    """Build the daily message.

    scan, sensors: the latest records (or None). Freshness is judged here against `now`,
        so pass them unfiltered (store.latest_scan(max_age=None)).
    now: timezone-aware current time; times in the message are shown in its timezone.
    photo_ok: tells whether a stored photo path can actually be sent. The text only says
        "photo attached" for photos that pass. Defaults to accepting every path.
    scan_command: the command that runs a scan by hand (SCAN_COMMAND), shown when the grower
        needs one. None: the message asks them to run the camera program instead.
    irrigation: watering advice (irrigation.advise); one line after the oranges.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    photo_ok = photo_ok or (lambda _path: True)

    sensor_line = _sensor_line(sensors, now)
    water_line = advice_line(irrigation, now.date()) if irrigation else None
    scan_time = _parse_time(scan.get("taken_at"), now) if scan else None

    if scan is None or scan_time is None or now - scan_time > SCAN_MAX_AGE:
        return Message(_join([_no_recent_scan(scan, scan_time, now, scan_command), water_line, sensor_line]))

    counts = _counts(scan)
    if sum(counts.values()) == 0:
        body = (
            f"<b>The last scan ({_when(scan_time, now)}) found no oranges.</b>\n"
            "Check that the camera points at the fruit and nothing blocks it, then "
            + _run_scan(scan_command, "scan again")
        )
        return Message(_join([body, water_line, sensor_line, _footer(scan, scan_time, now, with_time=False)]))
    footer = _footer(scan, scan_time, now)

    photos = _mold_photos(scan, photo_ok)
    whole_scan = len(photos) == 1 and photos[0].path == scan.get("image")
    note = " (photo attached)" if whole_scan else _photo_note(counts["mold"], len(photos))
    body = _headline(counts, note) + "\n\n" + "\n".join(_actions(scan, counts))
    return Message(_join([body, water_line, sensor_line, footer]), tuple(photos))


def to_plain(text: str) -> str:
    """Telegram HTML to plain text, for printing in a terminal."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


# --- the parts of the message ------------------------------------------------


def _headline(counts: Mapping[str, int], photo_note: str) -> str:
    mold = counts["mold"]
    parts = [f"{counts[k]} {name}" for k, name in
             (("ripe", "ready to pick"), ("ripening", "ripening"), ("unripe", "unripe")) if counts[k]]
    if mold:
        parts.append(f"{mold} possible mold{photo_note}")
        text = ", ".join(parts) + (": remove it today." if mold == 1 else ": remove them today.")
    elif counts["ripe"]:
        text = ", ".join(parts) + "."
    else:
        text = "Nothing to pick today."
    return f"<b>{text}</b>"


def _photo_note(mold: int, photo_count: int) -> str:
    if photo_count == 0:
        return ""
    if photo_count >= mold:
        return " (photo attached)" if mold == 1 else " (photos attached)"
    return f" (photo of {photo_count} attached)" if photo_count == 1 else f" (photos of {photo_count} attached)"


def _actions(scan: Mapping[str, Any], counts: Mapping[str, int]) -> list[str]:
    lines = []
    mold, ripe, ripening, unripe = counts["mold"], counts["ripe"], counts["ripening"], counts["unripe"]
    if mold:
        line = ("Remove the fruit with possible mold today, before the mold spreads." if mold == 1 else
                f"Remove the {mold} fruits with possible mold today, before the mold spreads.")
        if any(f.get("confidence") == "low" for f in _fruits(scan) if f.get("label") == "mold"):
            line += " The model is not sure about every one, so check by eye first."
        lines.append(line)
    if ripe:
        lines.append("Pick the orange that is ready." if ripe == 1 else f"Pick the {ripe} oranges that are ready.")
    elif mold:
        lines.append("Nothing is ready to pick yet.")
    if ripening:
        lines.append("Check the ripening one again in a few days." if ripening == 1 else
                     f"Check the {ripening} ripening ones again in a few days.")
    if unripe:
        lines.append("Leave the unripe one on the tree." if unripe == 1 else
                     f"Leave the {unripe} unripe ones on the tree.")
    return lines


def _no_recent_scan(scan: Mapping[str, Any] | None, scan_time: datetime | None, now: datetime,
                    scan_command: str | None) -> str:
    if scan is None:
        last = "There are no scans yet."
    elif scan_time is None:
        last = "The last scan has no readable time."
    else:
        last = f"The last one was {_when(scan_time, now)}."
    return (
        "<b>No scan in the last 24 hours.</b>\n"
        f"{last} Check that the laptop is on and the webcam is connected, then "
        + _run_scan(scan_command, "run a scan")
        + "\nThen send /status."
    )


def _run_scan(scan_command: str | None, verb: str) -> str:
    if scan_command:
        return f"{verb}:\n<code>{_esc(scan_command)}</code>"
    return f"{verb} with the camera program."


def _sensor_line(sensors: Mapping[str, Any] | None, now: datetime) -> str | None:
    if not sensors:
        return None
    taken = _parse_time(sensors.get("taken_at"), now)
    if taken is None or now - taken > SENSOR_MAX_AGE:
        return None
    parts = []
    soil = _number(sensors.get("soil_moisture_pct"))
    if soil is not None:
        parts.append(f"soil moisture {_fmt(soil)}%")
    temp = _number(sensors.get("temperature_c"))
    if temp is not None:
        parts.append(f"{_fmt(temp)} °C ({temp * 9 / 5 + 32:.0f} °F)")
    hum = _number(sensors.get("humidity_pct"))
    if hum is not None:
        parts.append(f"humidity {_fmt(hum)}%")
    wind = _number(sensors.get("wind_ms"))
    if wind is not None:
        parts.append(f"wind {_fmt(wind)} m/s")
    if not parts:
        return None
    label = "Sensors (simulated)" if sensors.get("simulated") is True else "Sensors"
    return f"{label} at {_clock(taken, now)}: " + ", ".join(parts) + "."


def _footer(scan: Mapping[str, Any], scan_time: datetime, now: datetime, *,
            with_time: bool = True) -> str | None:
    source = " from a saved photo" if scan.get("source") == "file" else ""
    lines = [f"Scan{source}: {_when(scan_time, now)}."] if with_time else []
    model = scan.get("model")
    if scan.get("demo"):
        lines.append("Demo data: the camera isn't connected yet, so this scan is an example.")
    elif isinstance(model, str) and "heuristic" in model.lower():
        lines.append("Labels come from a colour check until the trained model is plugged in.")
    return "<i>" + "\n".join(lines) + "</i>" if lines else None


def _mold_photos(scan: Mapping[str, Any], photo_ok: Callable[[str], bool]) -> list[Photo]:
    molds = [f for f in _fruits(scan) if f.get("label") == "mold"]
    molds.sort(key=lambda f: _CONFIDENCE_RANK.get(f.get("confidence"), 3))
    photos = []
    for fruit in molds:
        crop = fruit.get("crop")
        if not isinstance(crop, str) or not crop or not photo_ok(crop):
            continue
        conf = fruit.get("confidence")
        conf_text = f" ({_esc(conf)} confidence)" if conf in _CONFIDENCE_RANK else ""
        photos.append(Photo(crop, f"Possible mold, fruit {_esc(fruit.get('id', '?'))}{conf_text}."))
        if len(photos) == MAX_PHOTOS:
            break
    if not photos and molds:
        # No crop to send: fall back to the whole scan image, once.
        image = scan.get("image")
        if isinstance(image, str) and image and photo_ok(image):
            photos.append(Photo(image, "Whole scan. Look for the fruit with possible mold."))
    return photos


# --- helpers -----------------------------------------------------------------


def _fruits(scan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    fruits = scan.get("fruits")
    return [f for f in fruits if isinstance(f, Mapping)] if isinstance(fruits, list) else []


def _counts(scan: Mapping[str, Any]) -> dict[str, int]:
    summary = scan.get("summary")
    if isinstance(summary, Mapping):
        return {k: v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0
                for k, v in ((k, summary.get(k, 0)) for k in LABELS)}
    fruits = _fruits(scan)
    return {k: sum(1 for f in fruits if f.get("label") == k) for k in LABELS}


def _parse_time(value: Any, now: datetime) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=now.tzinfo)  # contract says times carry an offset; assume local if not
    return t


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return float(value)


def _fmt(value: float) -> str:
    return f"{value:.0f}" if value == int(value) else f"{value:.1f}"


def _clock(t: datetime, now: datetime) -> str:
    local = t.astimezone(now.tzinfo)
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def _when(t: datetime, now: datetime) -> str:
    local, today = t.astimezone(now.tzinfo), now.date()
    if local.date() == today:
        return f"today at {_clock(t, now)}"
    if local.date() == today - timedelta(days=1):
        return f"yesterday at {_clock(t, now)}"
    return f"on {local:%A}, {local:%b} {local.day} at {_clock(t, now)}"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _join(blocks: list[str | None]) -> str:
    return "\n\n".join(b for b in blocks if b)
