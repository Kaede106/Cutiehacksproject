"""Watering from the bot, with fake Telegram objects: /water_now, auto mode and results."""
import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler

from farm import irrigation_control as ic
from farm.bot import harvest
from farm.bot.app import build_application
from farm.bot.autowater import CANCEL, AutoWater, confirm_keyboard, load_settings
from farm.bot.config import ConfigError
from farm.bot.irrigation import NOT_TODAY, WATER_TODAY, Advice
from farm.common import store

from test_handlers import LA, context, data, handlers, run, update  # noqa: F401

CHAT = 111


def soil_reading(pct, simulated=False):
    record = {"soil_moisture_pct": pct, "temperature_c": 22.0, "humidity_pct": 50.0, "wind_ms": None}
    if simulated:
        record["simulated"] = True
    store.append_sensors(record)


def advice(cadence=WATER_TODAY):
    return lambda config, now: Advice(cadence, None, "Soil moisture is 28%, below 35%.")


def water(data, auto=False, allowed=str(CHAT), cadence=WATER_TODAY, **settings):
    h = handlers(data, allowed=allowed)
    return AutoWater(h, advice(cadence), ic.WaterSettings(auto=auto, **settings))


def tap(chat_id, action):
    u = update(chat_id)
    u.callback_query = SimpleNamespace(data=action, answer=AsyncMock(), edit_message_text=AsyncMock())
    return u


def keyboard(reply_call):
    markup = reply_call.kwargs["reply_markup"]
    return {b.text: b.callback_data for row in markup.inline_keyboard for b in row}


def ask(w, chat_id=CHAT, args=None):
    u, ctx = update(chat_id, "/water_now"), context()
    ctx.args = args or []
    run(w.water_now(u, ctx))
    return u.effective_message.reply_text.call_args


# ---------------------------------------------------------------- settings and wiring

def test_bad_watering_setting_is_a_config_error(monkeypatch):
    monkeypatch.setenv("MAX_WATER_SECONDS", "90")
    with pytest.raises(ConfigError, match="MAX_WATER_SECONDS"):
        load_settings()


def test_auto_mode_is_off_by_default(data, monkeypatch):
    monkeypatch.delenv("AUTO_WATER", raising=False)
    app = build_application(handlers(data).config)
    names = {job.name for job in app.job_queue.jobs()}
    assert "water-results" in names and "auto-water" not in names
    assert any(isinstance(h, CommandHandler) and "water_now" in h.commands for h in app.handlers[0])


def test_auto_mode_on_schedules_the_job(data, monkeypatch):
    monkeypatch.setenv("AUTO_WATER", "1")
    app = build_application(handlers(data).config)
    (job,) = [j for j in app.job_queue.jobs() if j.name == "auto-water"]
    assert job.job.trigger.interval == timedelta(minutes=10)


def test_watering_buttons_are_routed_before_the_status_buttons(data):
    app = build_application(handlers(data).config)
    (mine,) = [h for h in app.handlers[-1] if isinstance(h, CallbackQueryHandler)]
    assert mine.pattern.match(CANCEL) and mine.pattern.match("v1:wn:go:8:0:1")
    assert not mine.pattern.match("v1:water") and not mine.pattern.match("v1:remind")


def test_watering_button_stops_other_handlers(data):
    w = water(data)
    with pytest.raises(ApplicationHandlerStop):
        run(w._button_only(tap(CHAT, CANCEL), context()))


# ---------------------------------------------------------------- automatic mode

def test_auto_off_sends_nothing_even_when_dry(data):
    soil_reading(20)
    w = water(data, auto=False)
    w.handlers.state.subscribe(CHAT, datetime.now(LA))
    ctx = context()
    run(w.auto_check(ctx))
    assert ic.read_commands() == []
    ctx.bot.send_message.assert_not_called()


def test_auto_on_waters_and_tells_subscribers(data):
    soil_reading(28)
    w = water(data, auto=True)
    w.handlers.state.subscribe(CHAT, datetime.now(LA))
    w.handlers.state.subscribe(999, datetime.now(LA))  # not in ALLOWED_CHAT_IDS: never told
    ctx = context()
    run(w.auto_check(ctx))
    (command,) = ic.read_commands()
    assert command["requested_by"] == "auto" and command["seconds"] == 8
    assert command["reason"] == "Soil moisture is 28%, below 35%."
    ctx.bot.send_message.assert_awaited_once_with(CHAT, "Watering now for 8 s: soil at 28%.")


def test_auto_says_simulated(data):
    soil_reading(28, simulated=True)
    w = water(data, auto=True)
    w.handlers.state.subscribe(CHAT, datetime.now(LA))
    ctx = context()
    run(w.auto_check(ctx))
    assert ctx.bot.send_message.await_args.args[1] == "Watering now for 8 s: soil at 28% (simulated)."


def test_auto_does_nothing_unless_the_advice_is_water_today(data):
    soil_reading(28)
    w = water(data, auto=True, cadence=NOT_TODAY)
    ctx = context()
    run(w.auto_check(ctx))
    assert ic.read_commands() == []


def test_auto_never_waters_wet_soil(data):
    soil_reading(75)
    w = water(data, auto=True)
    w.handlers.state.subscribe(CHAT, datetime.now(LA))
    ctx = context()
    run(w.auto_check(ctx))
    assert ic.read_commands() == []
    ctx.bot.send_message.assert_not_called()


def test_auto_respects_cooldown_and_daily_cap(data):
    soil_reading(28)
    w = water(data, auto=True, cooldown_min=30, max_per_day=2)
    ctx = context()
    run(w.auto_check(ctx))
    run(w.auto_check(ctx))  # straight after: cooldown
    assert len(ic.read_commands()) == 1
    # Pretend the first ran 40 minutes ago: allowed again, then the daily cap stops a third.
    lines = (data / ic.COMMANDS_FILE).read_text(encoding="utf-8")
    earlier = (datetime.now(LA) - timedelta(minutes=40)).isoformat(timespec="seconds")
    first = json.loads(lines)
    first["taken_at"] = earlier
    (data / ic.COMMANDS_FILE).write_text(json.dumps(first) + "\n", encoding="utf-8")
    ic.append_result({"command_id": first["id"], "status": "done"})
    run(w.auto_check(ctx))
    assert len(ic.read_commands()) == 2
    # Make the second one old too; the cap (2 a day) now refuses.
    commands = ic.read_commands()
    commands[1]["taken_at"] = (datetime.now(LA) - timedelta(minutes=35)).isoformat(timespec="seconds")
    (data / ic.COMMANDS_FILE).write_text("".join(json.dumps(c) + "\n" for c in commands), encoding="utf-8")
    ic.append_result({"command_id": commands[1]["id"], "status": "done"})
    run(w.auto_check(ctx))
    assert len(ic.read_commands()) == 2


# ---------------------------------------------------------------- /water_now

def test_water_now_asks_to_confirm_and_queues_nothing_yet(data):
    soil_reading(28)
    call = ask(water(data))
    assert call.args[0] == "Water the grove for 8 s now? Soil is at 28%."
    buttons = keyboard(call)
    assert set(buttons) == {"Water 8 s", "Cancel"}
    assert all(len(v.encode()) <= 64 for v in buttons.values())
    assert ic.read_commands() == []


def test_water_now_confirm_queues_one_watering(data):
    soil_reading(28)
    w = water(data)
    go = keyboard(ask(w))["Water 8 s"]
    u = tap(CHAT, go)
    run(w.button(u, context()))
    (command,) = ic.read_commands()
    assert command["requested_by"] == f"chat:{CHAT}" and command["seconds"] == 8
    assert "Queued" in u.callback_query.edit_message_text.await_args.args[0]
    # A second tap on the same button hits the cooldown.
    u2 = tap(CHAT, go)
    run(w.button(u2, context()))
    assert len(ic.read_commands()) == 1
    assert u2.callback_query.edit_message_text.await_args.args[0].startswith("Nothing was sent.")


def test_water_now_cancel_sends_nothing(data):
    soil_reading(28)
    w = water(data)
    ask(w)
    u = tap(CHAT, CANCEL)
    run(w.button(u, context()))
    assert ic.read_commands() == []
    assert u.callback_query.edit_message_text.await_args.args[0] == "Cancelled. Nothing was sent to the pump."


def test_water_now_on_wet_soil_needs_water_anyway(data):
    soil_reading(80)
    w = water(data)
    call = ask(w)
    assert "80%, above the wet-enough level of 60%" in call.args[0] and call.args[0].endswith("anyway?")
    buttons = keyboard(call)
    assert "Water anyway (8 s)" in buttons
    assert ic.read_commands() == []
    # A forged plain confirm (override=0) for wet soil sends nothing.
    plain = buttons["Water anyway (8 s)"].replace(":8:1:", ":8:0:")
    run(w.button(tap(CHAT, plain), context()))
    assert ic.read_commands() == []
    run(w.button(tap(CHAT, buttons["Water anyway (8 s)"]), context()))
    assert len(ic.read_commands()) == 1


def test_water_now_without_soil_reading_needs_water_anyway(data):
    call = ask(water(data))
    assert "no fresh soil moisture reading" in call.args[0]
    assert "Water anyway (8 s)" in keyboard(call)


def test_water_now_caps_the_seconds(data):
    soil_reading(28)
    call = ask(water(data), args=["40"])
    assert "15 s (the most allowed is 15 s, MAX_WATER_SECONDS)" in call.args[0]
    assert "Water 15 s" in keyboard(call)


def test_water_now_bad_argument(data):
    call = ask(water(data), args=["lots"])
    assert "/water_now 8" in call.args[0]


def test_water_now_in_cooldown_refuses_without_buttons(data):
    soil_reading(28)
    w = water(data)
    ic.request(w.settings, now=datetime.now(LA), requested_by="auto", reason="", manual=True)
    call = ask(w)
    assert call.args[0].startswith("I can't water now. The last watering was 0 min ago.")
    assert "reply_markup" not in call.kwargs


def test_water_now_needs_an_allowlist(data):
    soil_reading(28)
    w = water(data, allowed=None)
    call = ask(w, chat_id=5)
    assert "ALLOWED_CHAT_IDS" in call.args[0]
    run(w.button(tap(5, confirm_keyboard(8, False, time.time()).inline_keyboard[0][0].callback_data), context()))
    assert ic.read_commands() == []


def test_water_now_ignores_chats_outside_the_allowlist(data):
    soil_reading(28)
    w = water(data)
    u, ctx = update(222, "/water_now"), context()
    run(w.water_now(u, ctx))
    u.effective_message.reply_text.assert_not_called()
    run(w.button(tap(222, confirm_keyboard(8, False, time.time()).inline_keyboard[0][0].callback_data), ctx))
    assert ic.read_commands() == []


def test_expired_confirm_button_does_nothing(data):
    soil_reading(28)
    w = water(data)
    old = confirm_keyboard(8, False, time.time() - 600).inline_keyboard[0][0].callback_data
    u = tap(CHAT, old)
    run(w.button(u, context()))
    assert ic.read_commands() == []
    assert "expired" in u.callback_query.edit_message_text.await_args.args[0]


# ---------------------------------------------------------------- results

def confirmed_watering(data, w, status, **extra):
    run(w.watch_results(context()))  # baseline
    soil_reading(28)
    _, command = ic.request(w.settings, now=datetime.now(LA), requested_by=f"chat:{CHAT}", reason="", manual=True)
    ic.append_result({"command_id": command["id"], "status": "sent", "seconds": 8})
    ic.append_result({"command_id": command["id"], "status": status, "seconds": 8, **extra})
    ctx = context()
    run(w.watch_results(ctx))
    return ctx


def test_board_confirmed_watering_is_logged_for_week(data):
    w = water(data)
    ctx = confirmed_watering(data, w, "done")
    ctx.bot.send_message.assert_awaited_once_with(CHAT, "Done: watered for 8 s. The board confirmed it.")
    (entry,) = harvest.entries(CHAT)
    assert entry["kind"] == "watered" and "demo" not in entry
    today = datetime.now(LA)
    assert f"Watered: {today:%a} {today:%b} {today.day}" in harvest.week_summary(CHAT, today)
    run(w.watch_results(ctx))  # nothing new: not logged twice
    assert len(harvest.entries(CHAT)) == 1


def test_simulated_watering_is_logged_as_demo_and_says_so(data):
    w = water(data)
    ctx = confirmed_watering(data, w, "done", simulated=True)
    assert "no water really ran" in ctx.bot.send_message.await_args.args[1]
    assert harvest.entries(CHAT) == []
    (entry,) = harvest.entries(CHAT, include_demo=True)
    assert entry["demo"] is True
    assert "Includes demo data" in harvest.week_summary(CHAT, datetime.now(LA))


@pytest.mark.parametrize("status, words", [("no_ack", "didn't confirm"), ("failed", "didn't run")])
def test_unconfirmed_watering_is_reported_not_logged(data, status, words):
    w = water(data)
    ctx = confirmed_watering(data, w, status, detail="no board connected to the laptop")
    assert words in ctx.bot.send_message.await_args.args[1]
    assert harvest.entries(CHAT, include_demo=True) == []


def test_auto_results_go_to_subscribers(data):
    w = water(data, auto=True)
    w.handlers.state.subscribe(CHAT, datetime.now(LA))
    run(w.watch_results(context()))
    soil_reading(28)
    run(w.auto_check(context()))
    (command,) = ic.read_commands()
    ic.append_result({"command_id": command["id"], "status": "done", "seconds": 8})
    ctx = context()
    run(w.watch_results(ctx))
    ctx.bot.send_message.assert_awaited_once_with(CHAT, "Done: watered for 8 s. The board confirmed it.")
    assert [e["kind"] for e in harvest.entries(CHAT)] == ["watered"]


def test_bridge_not_running_is_reported_once(data):
    w = water(data)
    run(w.watch_results(context()))
    old = datetime.now(LA) - timedelta(minutes=5)
    ic.append_command(ic.new_command(8, "", f"chat:{CHAT}", old))
    ctx = context()
    run(w.watch_results(ctx))
    run(w.watch_results(ctx))
    ctx.bot.send_message.assert_awaited_once()
    assert "sensor bridge isn't answering" in ctx.bot.send_message.await_args.args[1]
