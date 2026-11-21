"""Handlers with fake Telegram objects: access control, commands, the daily job, photos."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from telegram.error import Forbidden

from farm.bot.app import COMMANDS_LINE, Handlers, build_message
from farm.bot.chat import Conversation
from farm.bot.config import load_config
from farm.bot.state import State
from farm.common import store

LA = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    return tmp_path


def handlers(data, allowed=None):
    env = {"TELEGRAM_BOT_TOKEN": "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ"}
    if allowed:
        env["ALLOWED_CHAT_IDS"] = allowed
    return Handlers(load_config(env), State(data / "bot_state.json"))


def update(chat_id, text="/start", chat_type="private"):
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
                           effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()))


def context():
    return SimpleNamespace(bot=AsyncMock())


def run(coro):
    return asyncio.run(coro)


def add_scan(data, labels, crop="scans/x-1.jpg"):
    fruits = [{"id": i, "label": lab, "confidence": "high", "bbox": [0, 0, 1, 1],
               "crop": crop if lab == "mold" else None} for i, lab in enumerate(labels, start=1)]
    store.append_scan({"id": "x", "source": "webcam", "model": "color-heuristic-v1",
                       "image": "scans/x.jpg", "fruits": fruits})


@pytest.mark.parametrize("method", ["start", "stop", "status", "water", "help", "text", "unknown"])
def test_chats_outside_the_allowlist_are_ignored(data, method):
    h, u, ctx = handlers(data, allowed="111"), update(222, "hello"), context()
    run(getattr(h, method)(u, ctx))
    u.effective_message.reply_text.assert_not_called()
    ctx.bot.send_message.assert_not_called()
    assert h.state.chats() == []


def test_start_subscribes_an_allowed_chat(data):
    h, u = handlers(data, allowed="111, 333"), update(111)
    run(h.start(u, context()))
    assert h.state.chats() == [111]
    reply = u.effective_message.reply_text.call_args.args[0]
    assert "every day at 9:00 AM (America/Los_Angeles)" in reply
    assert "ALLOWED_CHAT_IDS" not in reply


def test_start_without_allowlist_logs_the_chat_id(data, caplog):
    h, u = handlers(data), update(555)
    with caplog.at_level("INFO", logger="farm.bot"):
        run(h.start(u, context()))
    assert "ALLOWED_CHAT_IDS=555" in caplog.text
    assert "ALLOWED_CHAT_IDS" not in u.effective_message.reply_text.call_args.args[0]


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
def test_public_mode_rejects_non_private_chats(data, chat_type):
    u, ctx = update(-222, "hola", chat_type), context()
    run(handlers(data).text(u, ctx))
    u.effective_message.reply_text.assert_not_called()
    ctx.bot.send_chat_action.assert_not_called()
    run(handlers(data, allowed="-222").text(u, ctx))
    u.effective_message.reply_text.assert_awaited_once()


def test_stop_unsubscribes(data):
    h = handlers(data)
    run(h.start(update(1), context()))
    u = update(1, "/stop")
    run(h.stop(u, context()))
    assert h.state.chats() == []
    assert "unsubscribed" in u.effective_message.reply_text.call_args.args[0]


def test_free_text_without_ai_matches_keywords(data):
    ctx = context()
    run(handlers(data).text(update(1, "what should I do with the moldy one?"), ctx))
    assert ctx.bot.send_message.call_args.args[0] == 1  # answered with today's status


def test_free_text_without_ai_and_no_keyword_lists_commands(data):
    u = update(1, "tell me a joke")
    run(handlers(data).text(u, context()))
    reply = u.effective_message.reply_text.call_args.args[0]
    assert reply.startswith("Ask me about your oranges") and "/status" in reply


def test_exhausted_quota_prefers_keyword_answer(data):
    h = handlers(data)
    client = Mock(post=AsyncMock())
    h.conversation = Conversation({"OPENAI_API_KEY": "fake-key", "CHAT_DAILY_LIMIT": "0"}, client)
    u, ctx = update(1, "When should I water?"), context()
    run(h.text(u, ctx))
    assert "watering advice" in ctx.bot.send_message.await_args.args[1]
    u.effective_message.reply_text.assert_not_called()
    client.post.assert_not_called()


def test_farm_context_failure_falls_back_without_model_call(data, monkeypatch, caplog):
    h = handlers(data)
    h.conversation = Conversation({"OPENAI_API_KEY": "fake-key"})
    h.conversation.reply = AsyncMock()

    def malformed(now):
        raise ValueError("malformed data")

    monkeypatch.setattr(h, "_farm_context", malformed)
    u, ctx = update(1, "any mold?"), context()
    run(h.text(u, ctx))
    h.conversation.reply.assert_not_called()
    ctx.bot.send_message.assert_awaited_once()
    assert "Could not prepare a chat answer" in caplog.text


def test_status_sends_text_and_the_mold_photo(data):
    (data / "scans").mkdir()
    (data / "scans" / "x-1.jpg").write_bytes(b"\xff\xd8\xff")
    add_scan(data, ["mold", "ripe"])
    ctx = context()
    run(handlers(data).status(update(9, "/status"), ctx))
    text = ctx.bot.send_message.call_args.args[1]
    assert text.startswith("<b>1 ready to pick, 1 possible mold (photo attached): remove it today.</b>")
    assert ctx.bot.send_message.call_args.kwargs["parse_mode"] == "HTML"
    assert ctx.bot.send_photo.call_args.kwargs["photo"] == (data / "scans" / "x-1.jpg").resolve()


def test_photo_outside_data_folder_is_never_sent(data):
    outside = data.parent / "private.jpg"
    outside.write_bytes(b"\xff\xd8\xff")
    add_scan(data, ["mold"], crop="../private.jpg")
    ctx = context()
    run(handlers(data).status(update(9), ctx))
    ctx.bot.send_photo.assert_not_called()
    ctx.bot.send_media_group.assert_not_called()
    assert "attached" not in ctx.bot.send_message.call_args.args[1]


def test_status_with_no_data(data):
    ctx = context()
    run(handlers(data).status(update(9), ctx))
    assert "No scan in the last 24 hours." in ctx.bot.send_message.call_args.args[1]


def test_daily_job_sends_to_allowed_subscribers_and_drops_blocked_ones(data):
    add_scan(data, ["ripe"])
    h = handlers(data, allowed="1,2")
    now = datetime.now(LA)
    for chat in (1, 2, 3):  # 3 subscribed before the allowlist was set
        h.state.subscribe(chat, now)
    ctx = context()

    async def send_message(chat_id, text, **kw):
        if chat_id == 2:
            raise Forbidden("bot was blocked by the user")

    ctx.bot.send_message.side_effect = send_message
    run(h.daily(ctx))
    assert [c.args[0] for c in ctx.bot.send_message.call_args_list] == [1, 2]
    assert h.state.chats() == [1, 3]


def test_build_message_reads_through_store_and_judges_age(data):
    store.append_scan({"id": "old", "taken_at": (datetime.now(LA) - timedelta(hours=30)).isoformat(),
                       "source": "webcam", "model": "color-heuristic-v1", "image": "scans/o.jpg",
                       "fruits": []})
    config = load_config({}, require_token=False)
    text = build_message(config).text
    assert "No scan in the last 24 hours." in text and "There are no scans yet." not in text
    store.append_sensors({"soil_moisture_pct": None, "temperature_c": 20.0, "humidity_pct": None,
                          "wind_ms": None, "simulated": True})
    assert "Sensors (simulated) at" in build_message(config).text


def test_water_command_reads_sensor_history(data):
    for minutes in (30, 10):
        store.append_sensors({"taken_at": (datetime.now(LA) - timedelta(minutes=minutes)).isoformat(),
                              "soil_moisture_pct": 25.0, "temperature_c": 20.0, "humidity_pct": None,
                              "wind_ms": None, "simulated": True})
    ctx = context()
    run(handlers(data).water(update(9, "/water"), ctx))
    text = ctx.bot.send_message.call_args.args[1]
    assert text.startswith("<b>Water today.</b>") and "simulated" in text
    assert ctx.bot.send_message.call_args.kwargs["parse_mode"] == "HTML"


def test_start_from_landing_skips_owner_hint_and_sends_status(data):
    h, u = handlers(data), update(777)
    ctx = context()
    ctx.args = ["landing"]
    run(h.start(u, ctx))
    assert h.state.chats() == [777]
    assert "ALLOWED_CHAT_IDS" not in u.effective_message.reply_text.call_args.args[0]
    assert ctx.bot.send_message.call_args.args[0] == 777


def test_start_again_does_not_resend_status(data):
    h = handlers(data)
    run(h.start(update(42), context()))
    ctx = context()
    run(h.start(update(42), ctx))
    ctx.bot.send_message.assert_not_called()
