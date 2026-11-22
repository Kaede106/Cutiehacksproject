"""Build the dashboard's JSON state from the shared data folder. Read-only, nothing is cached on disk.

The page shows ripeness only: `unripe`, `ripening` and `ripe` (shown as "ready to pick").
Any `mold` label and any `crop` field in the data are ignored.
"""
from __future__ import annotations

import math
import os
import re
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from farm.bot import irrigation, weather as weather_cache
from farm.common import store

from .settings import Settings

HARVEST_FILE = "harvest.jsonl"  # written by farm/bot/harvest.py
SHOWN = ("ripe", "ripening", "unripe")
WINDOW = timedelta(hours=24)
STALE_AFTER = timedelta(hours=1)  # the same age the store uses for "fresh" sensor readings
SPARK_POINTS = 96
FEED_LENGTH = 24
MAX_SCANS, MAX_SENSORS, MAX_HARVEST = 400, 20_000, 2_000
IMAGE_SUFFIXES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_IMAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_KIND_ORDER = {"ready": 0, "picked": 1, "watered": 2, "scan": 3, "sensors": 4}


def data_folder() -> Path:
    """The data folder, like store.data_dir() but without creating it: the dashboard only reads."""
    env = os.environ.get("CUTIEFARM_DATA")
    return Path(env) if env else Path(store.__file__).resolve().parent.parent / "data"


# --- images --------------------------------------------------------------------


def scan_image_path(folder: Path, name: str) -> Path | None:
    """A file under <folder>/scans/ for a flat file name like `20261121T090012-3f9a.jpg`, or None.

    Rejects anything that is not a plain file name: slashes, backslashes, `..`, drive letters,
    absolute paths, hidden names and unknown extensions. Symlinks out of scans/ are refused too.
    """
    if not isinstance(name, str) or not _IMAGE_NAME.fullmatch(name):
        return None
    if Path(name).suffix.lower() not in IMAGE_SUFFIXES or ".." in name:
        return None
    try:
        root = (folder / "scans").resolve(strict=True)
        path = (root / name).resolve(strict=True)
        if path.parent != root or not path.is_file():
            return None
    except (OSError, ValueError):
        return None
    return path


def _image_url(folder: Path, relative: Any) -> str | None:
    """`/scans/<name>?v=<mtime>` for a record's `image` ("scans/<name>"), if the file is servable."""
    if not isinstance(relative, str) or not relative.startswith("scans/"):
        return None
    path = scan_image_path(folder, relative[len("scans/"):])
    if path is None:
        return None
    return f"/scans/{path.name}?v={int(path.stat().st_mtime)}"


# --- small helpers ---------------------------------------------------------------


def _time(value: Any, tz) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    return t.replace(tzinfo=tz) if t.tzinfo is None else t


def _clock(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _records(name: str, limit: int) -> list[dict[str, Any]]:
    return list(deque(store._read(name), maxlen=limit))


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        return None
    x, y, w, h = (float(v) for v in value)
    return [x, y, w, h] if w > 0 and h > 0 and x >= 0 and y >= 0 else None


def _counts(fruits: list[dict[str, Any]]) -> dict[str, int]:
    return {label: sum(1 for f in fruits if f["label"] == label) for label in SHOWN}


def _placeholder_size(fruits: list[dict[str, Any]]) -> tuple[int, int]:
    """Canvas for a scan with no saved photo: the boxes, with an even margin all round."""
    boxes = [f["bbox"] for f in fruits if f["bbox"]]
    if not boxes:
        return 640, 360
    margin_x = max(min(b[0] for b in boxes), 24)
    margin_y = max(min(b[1] for b in boxes), 24)
    return (math.ceil(max(b[0] + b[2] for b in boxes) + margin_x),
            math.ceil(max(b[1] + b[3] for b in boxes) + margin_y))


# --- scans -----------------------------------------------------------------------


def _scans(settings: Settings) -> list[tuple[datetime, dict[str, Any]]]:
    out = []
    for record in _records(store.SCANS_FILE, MAX_SCANS):
        t = _time(record.get("taken_at"), settings.timezone)
        if t is not None:
            out.append((t, record))
    out.sort(key=lambda item: item[0])
    return out


def _fruits(record: dict[str, Any]) -> list[dict[str, Any]]:
    fruits = []
    for fruit in record.get("fruits") or []:
        if isinstance(fruit, dict) and fruit.get("label") in SHOWN:
            fruits.append({"label": fruit["label"], "bbox": _bbox(fruit.get("bbox"))})
    return fruits


LIVE_MAX_AGE_S = 5


def live_frame_path(folder: Path) -> Path | None:
    """<folder>/live/frame.jpg if it exists (the only file the live route serves)."""
    try:
        path = (folder / "live" / "frame.jpg").resolve(strict=True)
        root = (folder / "live").resolve(strict=True)
        return path if path.parent == root and path.is_file() else None
    except (OSError, ValueError):
        return None


def _live_state(folder: Path, now: datetime) -> dict[str, Any] | None:
    """The camera window's latest frame and detections, while they are fresh (a few seconds old)."""
    import json
    image = live_frame_path(folder)
    if image is None:
        return None
    try:
        meta = json.loads((folder / "live" / "frame.json").read_text(encoding="utf-8"))
        taken = datetime.fromisoformat(meta["taken_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if taken.tzinfo is None:
        taken = taken.replace(tzinfo=now.tzinfo)
    age = (now - taken).total_seconds()
    if age > LIVE_MAX_AGE_S or not isinstance(meta, dict):
        return None
    fruits = [f for f in meta.get("fruits", []) if isinstance(f, dict) and isinstance(f.get("bbox"), list)]
    return {
        "image": f"/live/frame.jpg?v={int(image.stat().st_mtime_ns // 1_000_000)}",
        "frame": {"w": int(meta.get("width") or 640), "h": int(meta.get("height") or 480)},
        "fruits": _fruits({"fruits": fruits}) if "_fruits" in globals() else fruits,
        "model": meta.get("model") if isinstance(meta.get("model"), str) else None,
        "age_s": max(0, int(age)),
    }


def _scan_state(folder: Path, scans: list[tuple[datetime, dict[str, Any]]], now: datetime) -> dict[str, Any] | None:
    if not scans:
        return None
    taken, record = scans[-1]
    fruits = _fruits(record)
    counts = _counts(fruits)
    previous = _counts(_fruits(scans[-2][1])) if len(scans) > 1 else None
    width, height = _placeholder_size(fruits)
    model, source = record.get("model"), record.get("source")
    return {
        "id": str(record.get("id") or ""),
        "taken_at": taken.isoformat(timespec="seconds"),
        "clock": _clock(taken.astimezone(now.tzinfo)),
        "age_s": max(0, int((now - taken).total_seconds())),
        "model": model if isinstance(model, str) and model else None,
        "source": source if isinstance(source, str) and source else None,
        "demo": record.get("demo") is True,
        "image": _image_url(folder, record.get("image")),
        "frame": {"w": width, "h": height},
        "fruits": fruits,
        "counts": counts,
        "previous": previous,
        "change": {k: counts[k] - previous[k] for k in SHOWN} if previous else None,
    }


# --- sensors and watering ------------------------------------------------------------

METRICS = (
    ("soil", "soil_moisture_pct", "Soil moisture", "%"),
    ("temperature", "temperature_c", "Temperature", "°C"),
    ("humidity", "humidity_pct", "Humidity", "%"),
)


def _sensor_rows(settings: Settings) -> list[dict[str, Any]]:
    rows = []
    for record in _records(store.SENSORS_FILE, MAX_SENSORS):
        t = _time(record.get("taken_at"), settings.timezone)
        if t is not None:
            rows.append({"t": t, "simulated": record.get("simulated") is True,
                         **{key: irrigation._number(record.get(field)) for key, field, _, _ in METRICS}})
    rows.sort(key=lambda r: r["t"])
    return rows


def _downsample(points: list[tuple[float, float]]) -> list[list[float]]:
    if len(points) <= SPARK_POINTS:
        return [[round(t), round(v, 1)] for t, v in points]
    size = len(points) / SPARK_POINTS
    out = []
    for i in range(SPARK_POINTS):
        chunk = points[int(i * size):int((i + 1) * size)]
        out.append([round(chunk[-1][0]), round(sum(v for _, v in chunk) / len(chunk), 1)])
    return out


def _sensors_state(rows: list[dict[str, Any]], now: datetime, settings: Settings) -> dict[str, Any]:
    start = now - WINDOW
    metrics = []
    for key, _, label, unit in METRICS:
        have = [r for r in rows if r[key] is not None]
        item: dict[str, Any] = {"key": key, "label": label, "unit": unit, "value": None, "age_s": None,
                                "clock": None, "stale": False, "simulated": False, "series": [],
                                "low": None, "high": None}
        if have:
            last = have[-1]
            age = max(0, int((now - last["t"]).total_seconds()))
            item.update(value=round(last[key], 1), age_s=age, clock=_clock(last["t"].astimezone(now.tzinfo)),
                        stale=age > STALE_AFTER.total_seconds(), simulated=last["simulated"])
            window = [(r["t"].timestamp(), r[key]) for r in have if start <= r["t"] <= now]
            if window:
                item.update(series=_downsample(window), low=round(min(v for _, v in window), 1),
                            high=round(max(v for _, v in window), 1))
        if key == "soil":
            item["threshold"] = settings.irrigation.water_below_pct
        metrics.append(item)
    return {"window": [round(start.timestamp()), round(now.timestamp())], "metrics": metrics,
            "any": any(m["value"] is not None for m in metrics)}


def _cached_weather(settings: Settings, folder: Path, today: date) -> irrigation.Weather | None:
    """The forecast the bot already cached today. The dashboard never goes to the network or writes."""
    irr = settings.irrigation
    if not irr.forecast_expected:
        return None
    key = [round(irr.latitude, 2), round(irr.longitude, 2)]
    cache = weather_cache._read_cache(folder / weather_cache.CACHE_FILE)
    try:
        if cache and cache.get("location") == key and cache.get("fetched_on") == today.isoformat():
            return weather_cache.parse_open_meteo(cache["payload"])
    except (KeyError, TypeError, ValueError):
        pass
    return weather_cache._stale(cache, key, today)


def _next_label(day: date | None, today: date) -> str | None:
    if day is None:
        return None
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%A}, {day:%b} {day.day}"


def _watering_state(folder: Path, now: datetime, settings: Settings) -> dict[str, Any] | None:
    history = _records(store.SENSORS_FILE, MAX_SENSORS)
    try:
        today = now.date()
        advice = irrigation.advise(history, _cached_weather(settings, folder, today), today,
                                   settings.irrigation, now=now)
    except Exception:  # advice must never take the page down
        return None
    cadence = advice.cadence
    if cadence in irrigation.INTERVAL_DAYS:
        title, tone = f"Water {cadence}", "ok"
    elif cadence == irrigation.WATER_TODAY:
        title, tone = "Water today", "now"
    elif cadence == irrigation.UNKNOWN:
        title, tone = "No advice yet", "unknown"
    else:
        title, tone = irrigation.headline(advice, today).rstrip("."), "ok"
    return {"cadence": cadence, "title": title, "tone": tone,
            "next_due": advice.next_due.isoformat() if advice.next_due else None,
            "next_label": _next_label(advice.next_due, today), "reason": advice.reason,
            "simulated": advice.simulated}


# --- activity feed ----------------------------------------------------------------------


def _harvest_events(settings: Settings, now: datetime) -> list[dict[str, Any]]:
    """Picked and watered entries. Undo markers cancel the chat's last real entry, as the bot does."""
    active: dict[Any, list[dict[str, Any]]] = {}
    demo: list[dict[str, Any]] = []
    for record in _records(HARVEST_FILE, MAX_HARVEST):
        if record.get("undo") is True:
            stack = active.get(record.get("chat_id"))
            if stack:
                stack.pop()
            continue
        count = record.get("count")
        if record.get("kind") not in ("picked", "removed", "watered") or type(count) is not int or count < 1:
            continue
        if record.get("demo"):
            demo.append(record)
        else:
            active.setdefault(record.get("chat_id"), []).append(record)
    events = []
    for record in [r for stack in active.values() for r in stack] + demo:
        t = _time(record.get("taken_at"), settings.timezone)
        if t is None or record["kind"] == "removed":  # removals were for mold, which is not shown
            continue
        if record["kind"] == "picked":
            n = record["count"]
            text, kind = f"{n} orange{'s' if n != 1 else ''} picked", "picked"
        else:
            text, kind = "Grove watered", "watered"
        events.append({"t": t, "kind": kind, "text": text, "flag": "demo" if record.get("demo") else None})
    return events


def _feed(scans, sensor_rows, settings: Settings, now: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    recent = scans[-12:]
    for i, (t, record) in enumerate(recent):
        counts = _counts(_fruits(record))
        flag = "demo" if record.get("demo") is True else None
        events.append({"t": t, "kind": "scan", "flag": flag,
                       "text": f"{counts['ripe']} ready to pick, {counts['ripening']} ripening, "
                               f"{counts['unripe']} unripe"})
        previous = _counts(_fruits(recent[i - 1][1]))["ripe"] if i > 0 else None
        if previous is not None and counts["ripe"] > previous:
            more = counts["ripe"] - previous
            events.append({"t": t, "kind": "ready", "flag": flag,
                           "text": f"{more} more orange{'s' if more != 1 else ''} ready to pick, "
                                   f"{counts['ripe']} in all"})
    events += _harvest_events(settings, now)
    if sensor_rows:
        last = sensor_rows[-1]
        parts = [f"soil {last['soil']:g}%" if last["soil"] is not None else None,
                 f"{last['temperature']:g} °C" if last["temperature"] is not None else None,
                 f"{last['humidity']:g}% humidity" if last["humidity"] is not None else None]
        text = ", ".join(p for p in parts if p)
        if text:
            events.append({"t": last["t"], "kind": "sensors", "text": text[0].upper() + text[1:],
                           "flag": "simulated" if last["simulated"] else None})
    events = [e for e in events if e["t"] <= now + timedelta(minutes=5)]
    events.sort(key=lambda e: (e["t"], -_KIND_ORDER[e["kind"]]), reverse=True)
    return [{"t": round(e["t"].timestamp()), "clock": _clock(e["t"].astimezone(now.tzinfo)),
             "age_s": max(0, int((now - e["t"]).total_seconds())), "kind": e["kind"], "text": e["text"],
             "flag": e["flag"]} for e in events[:FEED_LENGTH]]


# --- everything ---------------------------------------------------------------------------


def build_state(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    """The whole page as one JSON-able dict. Missing files give empty sections, never an error."""
    now = (now or datetime.now(settings.timezone)).astimezone(settings.timezone)
    folder = data_folder()
    state: dict[str, Any] = {
        "generated_at": round(now.timestamp()), "clock": f"{now.hour % 12 or 12}:{now.minute:02d}:{now.second:02d} {'AM' if now.hour < 12 else 'PM'}", "data_folder": folder.is_dir(),
        "scan": None, "live": None, "sensors": None, "watering": None, "feed": [], "notices": [],
    }
    if not state["data_folder"]:
        state["sensors"] = _sensors_state([], now, settings)
        return state
    scans = _scans(settings)
    rows = _sensor_rows(settings)
    state["scan"] = _scan_state(folder, scans, now)
    state["live"] = _live_state(folder, now)
    state["sensors"] = _sensors_state(rows, now, settings)
    state["watering"] = _watering_state(folder, now, settings)
    state["feed"] = _feed(scans, rows, settings, now)
    if state["scan"] and state["scan"]["demo"]:
        state["notices"].append({"key": "demo", "text": "Demo scan, not the real grove"})
    if any(m["simulated"] for m in state["sensors"]["metrics"]) or (state["watering"] or {}).get("simulated"):
        state["notices"].append({"key": "simulated", "text": "Simulated sensors, not measured"})
    return state
