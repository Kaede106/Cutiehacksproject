"""Pure harvest forecast from recent scan history and logged picks.

Estimates how fast oranges reach the `ripe` stage (adjusted for logged picks)
and projects when the oranges currently `ripening` should be ready to pick.
Returns None whenever the history is too short, flat, noisy or inconsistent.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Literal, Mapping

RIPENESS_LABELS = ("unripe", "ripening", "ripe")
HARVEST_KINDS = ("picked", "removed", "watered")

MIN_SCANS = 3
MIN_SPAN = timedelta(days=2)
WINDOW_DAYS = 14
MAX_LATEST_AGE = timedelta(days=3)
MIN_RATE_PER_DAY = 0.15
MIN_R2 = 0.65
MAX_DROP = 1
MAX_HORIZON_DAYS = 30.0

Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Forecast:
    ready_by: date | None
    count: int
    basis_days: int
    confidence: Confidence
    text: str


@dataclass(frozen=True)
class _ScanPoint:
    t: datetime  # UTC
    unripe: int
    ripening: int
    ripe: int
    demo: bool


@dataclass(frozen=True)
class _PickPoint:
    t: datetime  # UTC
    count: int
    demo: bool


def forecast_harvest(
    scans: Iterable[Mapping[str, Any]],
    now: datetime,
    harvest_entries: Iterable[Mapping[str, Any]] = (),
) -> Forecast | None:
    """Estimate when the currently ripening oranges will be ready to pick.

    scans: scan records as stored in scans.jsonl (mold labels are ignored).
    now: timezone-aware current time; dates in the forecast use its timezone.
    harvest_entries: records from harvest.jsonl (raw with undo markers, or
        already replayed via harvest.entries).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    tz = now.tzinfo
    end = now.astimezone(timezone.utc)
    start = end - timedelta(days=WINDOW_DAYS)

    points = _parse_scans(scans, start, end, now)
    if len(points) < MIN_SCANS:
        return None

    first, latest = points[0], points[-1]
    span = latest.t - first.t
    if span < MIN_SPAN or end - latest.t > MAX_LATEST_AGE:
        return None
    if latest.ripening <= 0:
        return None

    is_demo = any(p.demo for p in points)
    picks = _parse_picks(harvest_entries, first.t, latest.t, now, include_demo=is_demo)
    if any(p.demo for p in picks):
        is_demo = True

    xs: list[float] = []
    cum_ripe: list[int] = []
    adjusted_totals: list[int] = []
    pick_idx = 0
    picked_so_far = 0
    for point in points:
        while pick_idx < len(picks) and picks[pick_idx].t <= point.t:
            picked_so_far += picks[pick_idx].count
            pick_idx += 1
        xs.append((point.t - first.t).total_seconds() / 86400.0)
        cum_ripe.append(point.ripe + picked_so_far)
        adjusted_totals.append(point.unripe + point.ripening + point.ripe + picked_so_far)

    if not _is_consistent(cum_ripe, adjusted_totals):
        return None

    net_gain = cum_ripe[-1] - cum_ripe[0]
    if net_gain < 1:
        return None

    fit = _fit_rate(xs, cum_ripe)
    if fit is None:
        return None
    rate, r2 = fit
    if rate < MIN_RATE_PER_DAY or r2 < MIN_R2:
        return None

    count = latest.ripening
    days_needed = count / rate
    if days_needed > MAX_HORIZON_DAYS:
        return None

    basis_days = max(2, round(span.total_seconds() / 86400.0))
    max_drop = _max_drop(cum_ripe)
    confidence = _confidence(len(points), basis_days, r2, net_gain, max_drop)

    today = now.date()
    latest_day = latest.t.astimezone(tz).date()
    ready_by = max(today, latest_day + timedelta(days=max(1, round(days_needed))))
    text = _format_text(count, latest.ripe, ready_by, today, basis_days, confidence, is_demo)
    return Forecast(ready_by=ready_by, count=count, basis_days=basis_days, confidence=confidence, text=text)


def forecast_line(prediction: Forecast | None) -> str | None:
    """One Telegram-HTML line for a forecast, or None."""
    return html.escape(prediction.text, quote=False) if prediction is not None else None


def week_forecast_line(
    scans: Iterable[Mapping[str, Any]],
    now: datetime,
    harvest_entries: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Optional newline-prefixed Telegram-HTML forecast line for /week."""
    line = forecast_line(forecast_harvest(scans, now, harvest_entries))
    return f"\n{line}" if line else ""


def forecast_context_line(prediction: Forecast | str | None) -> str | None:
    """One plain-text line for chat.farm_context, or None."""
    if prediction is None:
        return None
    text = prediction.text if isinstance(prediction, Forecast) else str(prediction).strip()
    return f"Harvest forecast: {text}" if text else None


# --- parsing -----------------------------------------------------------------


def _parse_time(value: Any, now: datetime) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=now.tzinfo)
    return t.astimezone(timezone.utc)


def _ripeness_counts(scan: Mapping[str, Any]) -> tuple[int, int, int] | None:
    summary = scan.get("summary")
    if isinstance(summary, Mapping):
        counts = {
            k: v if type(v) is int and v > 0 else 0
            for k, v in ((k, summary.get(k, 0)) for k in RIPENESS_LABELS)
        }
        return counts["unripe"], counts["ripening"], counts["ripe"]
    fruits = scan.get("fruits")
    if isinstance(fruits, list):
        counts = dict.fromkeys(RIPENESS_LABELS, 0)
        for fruit in fruits:
            if isinstance(fruit, Mapping):
                label = fruit.get("label")
                if label in counts:
                    counts[label] += 1
        return counts["unripe"], counts["ripening"], counts["ripe"]
    return None


def _parse_scans(
    scans: Iterable[Mapping[str, Any]],
    start: datetime,
    end: datetime,
    now: datetime,
) -> list[_ScanPoint]:
    points: list[_ScanPoint] = []
    for record in scans:
        if not isinstance(record, Mapping):
            continue
        taken = _parse_time(record.get("taken_at"), now)
        if taken is None or taken < start or taken > end:
            continue
        counts = _ripeness_counts(record)
        if counts is None:
            continue
        unripe, ripening, ripe = counts
        points.append(_ScanPoint(taken, unripe, ripening, ripe, bool(record.get("demo"))))
    points.sort(key=lambda p: p.t)
    return points


def _parse_picks(
    harvest_entries: Iterable[Mapping[str, Any]],
    after: datetime,
    until: datetime,
    now: datetime,
    *,
    include_demo: bool,
) -> list[_PickPoint]:
    """Replay harvest entries per chat (applying undo markers) and return active picks in (after, until]."""
    by_chat: dict[Any, list[Mapping[str, Any]]] = {}
    demo_entries: list[Mapping[str, Any]] = []

    for record in harvest_entries:
        if not isinstance(record, Mapping):
            continue
        kind, count = record.get("kind"), record.get("count")
        if kind in HARVEST_KINDS and type(count) is int and count > 0:
            if record.get("demo"):
                if include_demo:
                    demo_entries.append(record)
            else:
                by_chat.setdefault(record.get("chat_id"), []).append(record)
        elif record.get("undo") is True:
            stack = by_chat.get(record.get("chat_id"))
            if stack:
                stack.pop()

    active = [r for stack in by_chat.values() for r in stack] + demo_entries
    picks: list[_PickPoint] = []
    for record in active:
        if record.get("kind") != "picked":
            continue
        taken = _parse_time(record.get("taken_at"), now)
        if taken is None or taken <= after or taken > until:
            continue
        picks.append(_PickPoint(taken, record["count"], bool(record.get("demo"))))
    picks.sort(key=lambda p: p.t)
    return picks


# --- trend fitting and checks ------------------------------------------------


def _max_drop(series: list[int]) -> int:
    peak = series[0]
    worst = 0
    for value in series[1:]:
        if value > peak:
            peak = value
        elif peak - value > worst:
            worst = peak - value
    return worst


def _is_consistent(cum_ripe: list[int], adjusted_totals: list[int]) -> bool:
    if _max_drop(cum_ripe) > MAX_DROP:
        return False
    min_total, max_total = min(adjusted_totals), max(adjusted_totals)
    if min_total == 0:
        return False
    if max_total - min_total > 4 and max_total > min_total * 2:
        return False
    return True


def _fit_rate(xs: list[float], ys: list[int]) -> tuple[float, float] | None:
    """Ordinary least squares slope (oranges/day) and R^2."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    var_x = sum((x - mx) ** 2 for x in xs)
    ss_tot = sum((y - my) ** 2 for y in ys)
    if var_x <= 0 or ss_tot <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = cov / var_x
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot
    return slope, r2


def _confidence(n_scans: int, basis_days: int, r2: float, net_gain: int, max_drop: int) -> Confidence:
    if n_scans >= 6 and basis_days >= 5 and r2 >= 0.85 and net_gain >= 3 and max_drop == 0:
        return "high"
    if n_scans >= 4 and basis_days >= 3 and r2 >= 0.75 and net_gain >= 2:
        return "medium"
    return "low"


# --- wording -----------------------------------------------------------------


def _when_phrase(ready_by: date, today: date, confidence: Confidence) -> str:
    delta = (ready_by - today).days
    if confidence == "low":
        if delta <= 0:
            return "in the next day or two"
        lo = max(today + timedelta(days=1), ready_by - timedelta(days=1))
        hi = ready_by + timedelta(days=1)
        if (hi - today).days <= 6:
            return f"between {lo:%A} and {hi:%A}"
        return f"between {lo:%b} {lo.day} and {hi:%b} {hi.day}"
    if delta <= 0:
        return "around today"
    if delta == 1:
        return "around tomorrow"
    if delta <= 6:
        return f"around {ready_by:%A}"
    return f"around {ready_by:%A}, {ready_by:%b} {ready_by.day}"


def _format_text(
    count: int,
    current_ripe: int,
    ready_by: date,
    today: date,
    basis_days: int,
    confidence: Confidence,
    is_demo: bool,
) -> str:
    if current_ripe > 0:
        subject = "About 1 more orange" if count == 1 else f"About {count} more"
    else:
        subject = "About 1 orange" if count == 1 else f"About {count} oranges"
    when = _when_phrase(ready_by, today, confidence)
    if is_demo:
        return f"{subject} should be ready to pick {when}, rough estimate from the last {basis_days} days (demo data)."
    return f"{subject} should be ready to pick {when} (rough estimate from the last {basis_days} days)."
