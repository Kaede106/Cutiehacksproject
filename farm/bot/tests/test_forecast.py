"""Harvest forecast estimation and integration hooks."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from farm.bot import demo, harvest
from farm.bot.app import Handlers, build_message
from farm.bot.chat import farm_context
from farm.bot.compose import compose, to_plain
from farm.bot.config import load_config
from farm.bot.forecast import Forecast, forecast_harvest
from farm.bot.state import State
from farm.common import store

LA = ZoneInfo("America/Los_Angeles")
TOKYO = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=LA)  # Saturday, Nov 21, 2026


def make_scan(
    when: datetime,
    *,
    unripe: int = 0,
    ripening: int = 0,
    ripe: int = 0,
    mold: int = 0,
    demo: bool = False,
    with_summary: bool = True,
) -> dict:
    fruits = (
        [{"id": i, "label": "unripe"} for i in range(unripe)]
        + [{"id": 100 + i, "label": "ripening"} for i in range(ripening)]
        + [{"id": 200 + i, "label": "ripe"} for i in range(ripe)]
        + [{"id": 300 + i, "label": "mold"} for i in range(mold)]
    )
    record: dict = {"taken_at": when.isoformat(timespec="seconds"), "fruits": fruits}
    if with_summary:
        record["summary"] = {"unripe": unripe, "ripening": ripening, "ripe": ripe, "mold": mold}
    if demo:
        record["demo"] = True
    return record


def pick_entry(when: datetime, count: int, *, chat_id: int | None = 1, kind: str = "picked", demo: bool = False) -> dict:
    record: dict = {"taken_at": when.isoformat(timespec="seconds"), "chat_id": chat_id, "kind": kind, "count": count}
    if demo:
        record["demo"] = True
    return record


# --- core forecast behavior --------------------------------------------------


def test_steady_ripening_trend():
    # +1 ripe orange per day for 6 days; 5 ripening now -> ready in ~5 days (Thursday, Nov 26).
    scans = [
        make_scan(NOW - timedelta(days=6 - day), unripe=11 - day, ripening=5, ripe=day)
        for day in range(7)
    ]
    result = forecast_harvest(scans, NOW)
    assert result is not None
    assert result.ready_by == date(2026, 11, 26)
    assert result.count == 5
    assert result.basis_days == 6
    assert result.confidence == "high"
    assert result.text == "About 5 more should be ready to pick around Thursday (rough estimate from the last 6 days)."


def test_steady_trend_ignores_mold_and_falls_back_to_fruits_list():
    scans = [
        make_scan(NOW - timedelta(days=4 - i), unripe=6 - i, ripening=3, ripe=i, mold=i % 2, with_summary=False)
        for i in range(5)
    ]
    result = forecast_harvest(scans, NOW)
    assert result is not None
    assert result.ready_by == date(2026, 11, 24)
    assert result.count == 3
    assert result.basis_days == 4
    assert result.confidence == "medium"
    assert "mold" not in result.text.lower()


def test_too_few_scans_or_too_short_span_returns_none():
    # Only 2 scans across 3 days
    two_scans = [
        make_scan(NOW - timedelta(days=3), unripe=5, ripening=4, ripe=0),
        make_scan(NOW, unripe=2, ripening=4, ripe=3),
    ]
    assert forecast_harvest(two_scans, NOW) is None

    # 4 scans, but all within 36 hours (< 2 days)
    short_span = [
        make_scan(NOW - timedelta(hours=36), unripe=6, ripening=4, ripe=0),
        make_scan(NOW - timedelta(hours=24), unripe=5, ripening=4, ripe=1),
        make_scan(NOW - timedelta(hours=12), unripe=4, ripening=4, ripe=2),
        make_scan(NOW, unripe=3, ripening=4, ripe=3),
    ]
    assert forecast_harvest(short_span, NOW) is None


def test_flat_trend_returns_none():
    scans = [
        make_scan(NOW - timedelta(days=6 - day), unripe=4, ripening=4, ripe=2)
        for day in range(7)
    ]
    assert forecast_harvest(scans, NOW) is None


def test_nothing_currently_ripening_returns_none():
    scans = [
        make_scan(NOW - timedelta(days=4 - day), unripe=4 - day, ripening=0, ripe=day)
        for day in range(5)
    ]
    assert forecast_harvest(scans, NOW) is None


def test_pick_in_the_middle_keeps_trend_intact():
    # True ripening rate is 1/day; grower picks 3 ripe oranges on day 3.
    scans = [
        make_scan(NOW - timedelta(days=6), unripe=7, ripening=4, ripe=1),
        make_scan(NOW - timedelta(days=4), unripe=5, ripening=4, ripe=3),
        make_scan(NOW - timedelta(days=2), unripe=3, ripening=4, ripe=2),  # 3 picked after day -4
        make_scan(NOW, unripe=1, ripening=3, ripe=5),
    ]
    picks = [pick_entry(NOW - timedelta(days=3), 3)]

    # Without the harvest log, the drop from 3 -> 2 flattens/distorts the fit (rate ~0.6/day -> 5 days).
    without_picks = forecast_harvest(scans, NOW)
    with_picks = forecast_harvest(scans, NOW, picks)
    assert with_picks is not None
    assert with_picks.ready_by == date(2026, 11, 24)  # 3 ripening at 1.0/day -> 3 days (Tue Nov 24)
    assert with_picks.count == 3
    assert with_picks.confidence == "medium"
    assert without_picks is None or without_picks.ready_by > with_picks.ready_by


def test_pick_in_the_middle_prevents_false_backward_drop():
    # Larger pick: visible ripe drops 4 -> 1 after picking 4, while ripening continues at 1/day.
    scans = [
        make_scan(NOW - timedelta(days=4), unripe=6, ripening=4, ripe=2),
        make_scan(NOW - timedelta(days=2), unripe=4, ripening=4, ripe=4),
        make_scan(NOW, unripe=2, ripening=4, ripe=2),  # +2 newly ripe, -4 picked
    ]
    assert forecast_harvest(scans, NOW) is None  # looks flat/backward without the pick

    picks = [pick_entry(NOW - timedelta(days=1), 4)]
    result = forecast_harvest(scans, NOW, picks)
    assert result is not None
    assert result.ready_by == date(2026, 11, 25)  # 4 ripening at 1/day -> Wed Nov 25
    assert result.count == 4


def test_harvest_undo_is_respected():
    scans = [
        make_scan(NOW - timedelta(days=4), unripe=6, ripening=4, ripe=2),
        make_scan(NOW - timedelta(days=2), unripe=4, ripening=4, ripe=4),
        make_scan(NOW, unripe=2, ripening=4, ripe=2),
    ]
    # Pick logged then undone -> back to looking flat/inconsistent -> None.
    entries = [
        pick_entry(NOW - timedelta(days=1), 4, chat_id=1),
        {"taken_at": (NOW - timedelta(hours=23)).isoformat(), "chat_id": 1, "undo": True},
    ]
    assert forecast_harvest(scans, NOW, entries) is None


def test_noisy_or_inconsistent_counts_return_none():
    # Oscillating ripe counts with no picks logged
    noisy = [
        make_scan(NOW - timedelta(days=4), unripe=5, ripening=4, ripe=1),
        make_scan(NOW - timedelta(days=3), unripe=3, ripening=2, ripe=5),
        make_scan(NOW - timedelta(days=2), unripe=5, ripening=4, ripe=1),
        make_scan(NOW - timedelta(days=1), unripe=2, ripening=2, ripe=6),
        make_scan(NOW, unripe=4, ripening=4, ripe=2),
    ]
    assert forecast_harvest(noisy, NOW) is None

    # Sudden unlogged drop in ripe count even though overall trend looks positive
    unlogged_drop = [
        make_scan(NOW - timedelta(days=5), unripe=8, ripening=2, ripe=0),
        make_scan(NOW - timedelta(days=4), unripe=4, ripening=2, ripe=4),
        make_scan(NOW - timedelta(days=3), unripe=7, ripening=2, ripe=1),
        make_scan(NOW - timedelta(days=2), unripe=3, ripening=2, ripe=5),
        make_scan(NOW - timedelta(days=1), unripe=2, ripening=2, ripe=6),
        make_scan(NOW, unripe=0, ripening=2, ripe=8),
    ]
    assert forecast_harvest(unlogged_drop, NOW) is None

    # Camera shifted to a completely different branch (wildly inconsistent totals)
    shifted_camera = [
        make_scan(NOW - timedelta(days=4), unripe=2, ripening=2, ripe=1),
        make_scan(NOW - timedelta(days=2), unripe=20, ripening=15, ripe=5),
        make_scan(NOW, unripe=1, ripening=3, ripe=8),
    ]
    assert forecast_harvest(shifted_camera, NOW) is None


def test_demo_marking_only_when_basis_includes_demo_scans():
    demo_scans = [
        make_scan(NOW - timedelta(days=6 - day), unripe=11 - day, ripening=5, ripe=day, demo=(day == 0))
        for day in range(7)
    ]
    result = forecast_harvest(demo_scans, NOW)
    assert result is not None
    assert "(demo data)" in result.text

    # An older demo scan outside the 14-day window should not mark real recent scans as demo.
    old_demo_plus_real = [make_scan(NOW - timedelta(days=20), unripe=10, ripening=2, ripe=0, demo=True)] + [
        make_scan(NOW - timedelta(days=6 - day), unripe=11 - day, ripening=5, ripe=day, demo=False)
        for day in range(7)
    ]
    real_result = forecast_harvest(old_demo_plus_real, NOW)
    assert real_result is not None
    assert "(demo data)" not in real_result.text


def test_date_formatting_respects_bot_timezone():
    # 2026-11-22 05:00 UTC is Saturday Nov 21 at 9:00 PM in Los Angeles,
    # Sunday Nov 22 at 5:00 AM in UTC, and Sunday Nov 22 at 2:00 PM in Tokyo.
    utc_now = datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)
    scans = [
        make_scan(utc_now - timedelta(days=6 - day), unripe=11 - day, ripening=5, ripe=day)
        for day in range(7)
    ]

    la_result = forecast_harvest(scans, utc_now.astimezone(LA))
    tokyo_result = forecast_harvest(scans, utc_now.astimezone(TOKYO))
    assert la_result is not None and tokyo_result is not None

    assert la_result.ready_by == date(2026, 11, 26)
    assert "around Thursday" in la_result.text
    assert tokyo_result.ready_by == date(2026, 11, 27)
    assert "around Friday" in tokyo_result.text


def test_low_confidence_uses_day_range_and_naive_now_rejected():
    # 3 scans over 2 days -> low confidence -> day range instead of single day
    scans = [
        make_scan(NOW - timedelta(days=2), unripe=6, ripening=3, ripe=0),
        make_scan(NOW - timedelta(days=1), unripe=5, ripening=3, ripe=1),
        make_scan(NOW, unripe=4, ripening=3, ripe=2),
    ]
    result = forecast_harvest(scans, NOW)
    assert result is not None
    assert result.confidence == "low"
    assert "between Monday and Wednesday" in result.text

    # Low-confidence scan from yesterday with 1 day left -> never "between X and X"
    yesterday_scans = [
        make_scan(NOW - timedelta(days=3), unripe=6, ripening=1, ripe=0),
        make_scan(NOW - timedelta(days=2), unripe=5, ripening=1, ripe=1),
        make_scan(NOW - timedelta(days=1), unripe=4, ripening=1, ripe=2),
    ]
    soon = forecast_harvest(yesterday_scans, NOW)
    assert soon is not None
    assert soon.ready_by == NOW.date()
    assert "in the next day or two" in soon.text

    with pytest.raises(ValueError):
        forecast_harvest(scans, datetime(2026, 11, 21, 9, 0))


# --- integration hooks -------------------------------------------------------


def test_compose_adds_forecast_line_right_after_picking_line():
    pred = Forecast(
        ready_by=date(2026, 11, 26),
        count=5,
        basis_days=6,
        confidence="high",
        text="About 5 more should be ready to pick around Thursday (rough estimate from the last 6 days).",
    )
    scan = make_scan(NOW - timedelta(minutes=5), unripe=2, ripening=5, ripe=3)
    msg = compose(scan, None, NOW, forecast=pred)
    blocks = to_plain(msg.text).split("\n\n")
    assert blocks[0].startswith("3 ready to pick today")
    assert blocks[1] == pred.text
    assert "!" not in msg.text
    assert all(ord(c) < 0x2190 for c in msg.text)
    assert not re.search(r"&(?!amp;|lt;|gt;|quot;)", msg.text)


def test_week_summary_includes_forecast_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    demo.seed(NOW, week=True)
    text = harvest.week_summary(1, NOW)
    assert "About 5 more should be ready to pick" in text
    assert "(demo data)" in text


def test_farm_context_and_app_builders_include_forecast(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    for day in range(7):
        store.append_scan(make_scan(NOW - timedelta(days=6 - day), unripe=11 - day, ripening=5, ripe=day))

    config = load_config({"TELEGRAM_BOT_TOKEN": "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ"})
    daily = build_message(config, NOW)
    assert "About 5 more should be ready to pick around Thursday" in to_plain(daily.text)

    h = Handlers(config, State(tmp_path / "bot_state.json"))
    ctx = h._farm_context(NOW)
    assert "Harvest forecast: About 5 more should be ready to pick around Thursday" in ctx

    # Direct farm_context helper accepts both Forecast and plain string
    direct = farm_context(None, None, None, NOW, forecast="About 5 more around Thursday.")
    assert "Harvest forecast: About 5 more around Thursday." in direct
