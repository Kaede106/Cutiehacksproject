"""Harvest parsing, disk storage, Telegram handlers and demo week seeding."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, MessageEntity, Update
from telegram.ext import CommandHandler

from farm.bot import __main__ as cli, demo, harvest
from farm.bot.app import COMMANDS, build_application
from farm.common import store

from test_handlers import LA, context, data, handlers, run, update  # noqa: F401


NOW = datetime(2026, 11, 21, 12, tzinfo=LA)


@pytest.mark.parametrize(("text", "expected"), [
    ("picked 3", ("picked", 3)),
    ("  I picked 3 oranges.  ", ("picked", 3)),
    ("he recogido 3", ("picked", 3)),
    ("Recogí 3 naranjas", ("picked", 3)),
    ("recogi\u0301 3 naranjas hoy", ("picked", 3)),
    ("I removed 1 moldy orange", ("removed", 1)),
    ("removed the moldy one", ("removed", 1)),
    ("quité 1 con hongo", ("removed", 1)),
    ("I watered", ("watered", 1)),
    ("watered", ("watered", 1)),
    ("he regado", ("watered", 1)),
    ("regué", ("watered", 1)),
    ("Regué los naranjos hoy!", ("watered", 1)),
])
def test_completed_actions_are_recognized(text, expected):
    assert harvest.parse_text(text) == expected


@pytest.mark.parametrize("text", [
    "should I pick 3?", "should I pick 3", "did I pick 3?",
    "I picked 3?", "I picked 3 oranges, right?", "I picked 3 or 4",
    "I picked 3 oranges if that counts", "I picked 3. Should I pick more?",
    "if I picked 3 oranges", "She picked 3 oranges", "I didn't pick 3",
    "I will pick 3", "pick 3", "I picked oranges", "picked 0",
    "picked -3", "picked 1.5", "picked 3.0 oranges", "picked 3-5",
    "picked 3 dozen oranges", "picked 3 oranges yesterday",
    "removed some moldy oranges", "removed the moldy one?",
    "should I water today?", "did you water", "I watered?",
    "I watered 2", "I already watered or maybe not",
    "¿riego hoy?", "riego hoy", "¿he regado?", "regué?",
    "¿recogí 3 naranjas?", "recogí 3 naranjas?", "debería recoger 3",
    "recogí 3 naranjas o 4", "si recogí 3 naranjas",
    "no he recogido 3", "voy a recoger 3", "él recogió 3",
    "recogí naranjas", "recogí 3,5 naranjas", "recogí 3 naranjas ayer",
    "quité con hongo", "¿quité 1 con hongo?", "no regué",
    "he regado pero no sé cuándo", 'I said "picked 3"', "picked 3 <b>oranges</b>",
])
def test_uncertain_or_incomplete_statements_are_left_to_chat(text):
    assert harvest.parse_text(text) is None


@pytest.mark.parametrize(("text", "expected"), [
    ("/picked 3", ("picked", 3)),
    ("/removed 1", ("removed", 1)),
    ("/watered", ("watered", 1)),
    ("/picked@CutieFarmBot   3", ("picked", 3)),
    ("/watered@CutieFarmBot", ("watered", 1)),
    ("/picked", None),
    ("/picked 3?", None),
    ("/removed 1 orange", None),
    ("/removed 0", None),
    ("/removed -1", None),
    ("/watered 3", None),
])
def test_commands_require_the_right_arguments(text, expected):
    assert harvest.parse_command(text) == expected


def test_storage_and_undo_are_append_only_and_scoped_to_chat(data):
    harvest.append_entry(1, "picked", 3, "  recogí 3 naranjas  ", now=NOW)
    harvest.append_entry(2, "watered", 1, "/watered", now=NOW)
    harvest.append_entry(1, "removed", 1, "/removed 1", now=NOW)
    path = data / "harvest.jsonl"
    before = path.read_bytes()
    assert len(before.splitlines()) == 3 and before.endswith(b"\n")
    assert json.loads(before.splitlines()[0]) == {
        "taken_at": NOW.isoformat(), "chat_id": 1, "kind": "picked",
        "count": 3, "text": "  recogí 3 naranjas  ",
    }
    assert harvest.undo(1)
    assert path.read_bytes().startswith(before)
    assert [r["kind"] for r in harvest.entries(1)] == ["picked"]
    assert [r["kind"] for r in harvest.entries(2)] == ["watered"]
    assert harvest.undo(1)
    assert not harvest.undo(1)
    harvest.append_entry(1, "watered", 1, "he regado")
    assert [r["kind"] for r in harvest.entries(1)] == ["watered"]


@pytest.mark.parametrize("count,expected", [("0", None), ("1", 1), ("10000", 10000), ("10001", None),
                                           ("9" * 5000, None)])
def test_harvest_parsers_bound_counts(count, expected):
    result = ("picked", expected) if expected is not None else None
    assert harvest.parse_command(f"/picked {count}") == result
    assert harvest.parse_text(f"I picked {count} oranges") == result


def test_harvest_limit_is_per_chat_and_day_and_shared_by_concurrent_updates(data):
    for _ in range(24):
        harvest.append_entry(1, "picked", 1, "/picked 1", now=NOW)
        assert harvest.undo(1, now=NOW)
    updates = [update(1, "/watered"), update(1, "picked 2"), update(1, "removed 1")]

    async def record():
        return await asyncio.gather(*(harvest.maybe_record(1, u.effective_message, now=NOW, command=i == 0)
                                      for i, u in enumerate(updates)))

    assert run(record()) == [True, True, True]
    assert sum(u.effective_message.reply_text.await_args.args[0] == harvest.WRITE_LIMIT_NOTICE for u in updates) == 1
    with pytest.raises(harvest.WriteLimitReached):
        harvest.undo(1, now=NOW)
    assert len(list(store._read(harvest.HARVEST_FILE))) == 50
    harvest.append_entry(2, "picked", 1, "picked 1", now=NOW)
    harvest.append_entry(1, "picked", 1, "picked 1", now=NOW + timedelta(days=1))


@pytest.mark.parametrize("text,entities", [("picked 3", ()), ("/picked 3", (MessageEntity("bot_command", 0, 7),))])
@pytest.mark.parametrize("ordinary,edited", [("message", "edited_message"), ("channel_post", "edited_channel_post")])
def test_edited_harvest_updates_are_ignored(data, text, entities, ordinary, edited):
    app = build_application(handlers(data).config)
    message = Message(1, NOW, Chat(1, "private"), text=text, entities=entities)
    message.set_bot(SimpleNamespace(username="CutieFarmBot"))
    assert any(handler.check_update(Update(1, **{ordinary: message})) for handler in app.handlers[0])
    assert not any(handler.check_update(Update(2, **{edited: message})) for handler in app.handlers[0])


def add_scan(taken_at, labels, **flags):
    store.append_scan({
        "taken_at": taken_at.isoformat(),
        "fruits": [{"label": label} for label in labels],
        **flags,
    })


def test_week_with_no_data_or_only_one_scan(data):
    text = harvest.week_summary(1, NOW)
    assert "Not enough scan data" in text
    assert "No harvest activity logged" in text
    assert "demo" not in text and "simulated" not in text
    add_scan(NOW, ["ripe"], demo=True)
    text = harvest.week_summary(1, NOW)
    assert "Not enough scan data" in text
    assert "Includes demo data" in text


def test_week_orders_scans_and_counts_only_recent_active_entries_for_this_chat(data):
    add_scan(NOW, ["ripe", "ripe", "ripening", "mold"])
    add_scan(NOW - timedelta(days=7), ["unripe", "unripe"])
    add_scan(NOW - timedelta(days=3), ["ripe"], simulated=True)
    add_scan(NOW - timedelta(days=7, seconds=1), ["mold"], demo=True)
    add_scan(NOW + timedelta(seconds=1), [], demo=True)

    def action(chat_id, kind, count, when, text="<b>original & text</b>"):
        harvest.append_entry(chat_id, kind, count, text, taken_at=when.isoformat())

    action(1, "picked", 3, NOW - timedelta(days=7))
    action(1, "picked", 2, NOW)
    action(1, "removed", 1, NOW - timedelta(days=2))
    action(1, "removed", 8, NOW)
    assert harvest.undo(1)
    action(1, "picked", 10, NOW - timedelta(days=8))
    action(1, "picked", 10, NOW + timedelta(seconds=1))
    action(2, "picked", 10, NOW)
    action(1, "watered", 1, datetime.fromisoformat("2026-11-20T01:00:00+00:00"))
    action(1, "watered", 1, NOW.replace(day=19))
    action(1, "watered", 1, NOW)
    with (data / "scans.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"taken_at":"invalid"}\nnull\n{bad json}\n')
    text = harvest.week_summary(1, NOW)
    assert text.startswith("<b>Last 7 days</b>")
    assert "Ready 0 → 2 · Ripening 0 → 1 · Unripe 2 → 0 · Possible mold 0 → 1" in text
    assert "Picked 5 · Removed 1" in text
    assert "Watered: Thu Nov 19, Sat Nov 21" in text
    assert "Includes simulated data" in text and "demo" not in text
    assert "original" not in text


def test_free_text_logs_before_conversation_but_questions_still_reach_it(data):
    h, ctx = handlers(data), context()
    h.conversation = SimpleNamespace(enabled=True, reply=AsyncMock(return_value="Advice"))
    h._farm_context = lambda now: "Farm summary"
    u = update(1, "recogí 3 naranjas")
    run(h.text(u, ctx))
    u.effective_message.reply_text.assert_awaited_once_with("Logged: 3 picked today.")
    h.conversation.reply.assert_not_called()

    for question in ("should I pick 3?", "¿riego hoy?"):
        u = update(1, question)
        run(h.text(u, ctx))
        u.effective_message.reply_text.assert_awaited_once_with("Advice")
        assert h.conversation.reply.call_args.args[1] == question
    assert len(harvest.entries(1)) == 1


def test_command_registration_help_and_handlers(data):
    h, ctx = handlers(data), context()
    app = build_application(h.config)
    registered = {name for handler in app.handlers[0] if isinstance(handler, CommandHandler)
                  for name in handler.commands}
    wanted = {"picked", "removed", "watered", "undo", "week"}
    assert wanted <= registered
    assert wanted <= {name for name, _ in COMMANDS}
    help_update = update(1, "/help")
    run(h.help(help_update, ctx))
    assert all(f"/{command}" in help_update.effective_message.reply_text.call_args.args[0] for command in wanted)
    for text in ("/picked 3", "/removed 1", "/watered"):
        u = update(1, text)
        run(h.record_harvest(u, ctx))
        assert u.effective_message.reply_text.call_args.args[0].startswith("Logged:")
    u = update(1, "/picked 3?")
    run(h.record_harvest(u, ctx))
    assert "Use /picked 3" in u.effective_message.reply_text.call_args.args[0]
    assert len(harvest.entries(1)) == 3
    run(h.undo(update(1, "/undo"), ctx))
    u = update(1, "/week")
    run(h.week(u, ctx))
    reply = u.effective_message.reply_text.call_args
    assert reply.kwargs["parse_mode"] == "HTML"
    assert "Picked 3 · Removed 1\nWatered: no days logged" in reply.args[0]


@pytest.mark.parametrize(("method", "text"), [
    ("text", "picked 3"), ("record_harvest", "/picked 3"), ("undo", "/undo"), ("week", "/week"),
])
def test_harvest_handlers_respect_allowlist(data, method, text):
    harvest.append_entry(2, "picked", 1, "/picked 1")
    h, u, ctx = handlers(data, allowed="1"), update(2, text), context()
    run(getattr(h, method)(u, ctx))
    u.effective_message.reply_text.assert_not_called()
    ctx.bot.send_message.assert_not_called()
    assert len(harvest.entries(2)) == 1


@pytest.mark.parametrize("flags", [[], ["--week"]])
def test_seed_demo_cli(data, monkeypatch, flags):
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    seed = demo.seed
    monkeypatch.setattr(demo, "seed", lambda **kwargs: seed(NOW, **kwargs))
    assert cli.main(["seed-demo", *flags]) == 0
    scans = list(store._read(store.SCANS_FILE))
    sensors = list(store._read(store.SENSORS_FILE))
    assert len(scans) == (7 if flags else 1) and all(s["demo"] is True for s in scans)
    assert sensors and all(s["simulated"] is True for s in sensors)
    assert scans[-1]["summary"] == {"ripe": 3, "ripening": 5, "unripe": 0, "mold": 1}
    assert (data / next(f["crop"] for f in scans[-1]["fruits"] if f["label"] == "mold")).is_file()
    if not flags:
        assert not (data / harvest.HARVEST_FILE).exists()
        return
    assert len({s["taken_at"][:10] for s in scans}) == 7
    examples = harvest.entries(987, include_demo=True)
    assert examples and all(r["demo"] is True for r in examples)
    assert not harvest.undo(987)
    text = harvest.week_summary(987, NOW)
    assert text.count("Includes demo data") == 2
    assert "Ready 0 → 3" in text
    assert "Picked 1 · Removed 1" in text
