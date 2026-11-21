"""Status buttons with fake Telegram objects and an offline reminder queue."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackQueryHandler

from farm.bot.app import build_application
from farm.bot.buttons import REMIND, WATER, StatusButtons

from test_handlers import add_scan, context, data, handlers, run, update  # noqa: F401


def callback(chat_id, action):
    u = update(chat_id)
    u.callback_query = SimpleNamespace(data=action, answer=AsyncMock())
    return u


def buttons(sent):
    markup = sent.kwargs["reply_markup"]
    return {button.text: button.callback_data for row in markup.inline_keyboard for button in row}


@pytest.mark.parametrize("entry", ["start", "status", "daily"])
def test_status_entry_points_attach_keyboard(data, entry):
    h, ctx = handlers(data), context()
    if entry == "daily":
        h.state.subscribe(9, datetime.now(UTC))
        run(h.daily(ctx))
    else:
        run(getattr(h, entry)(update(9), ctx))
    assert buttons(ctx.bot.send_message.await_args) == {
        "Watering details": WATER,
        "Remind me in 2 h": REMIND,
    }


def test_water_callback_matches_water_command(data):
    h, ctx = handlers(data), context()
    run(h.water(update(9), ctx))
    expected = ctx.bot.send_message.await_args
    ctx.bot.reset_mock()
    u = callback(9, WATER)
    run(StatusButtons(h).handle(u, ctx))
    u.callback_query.answer.assert_awaited_once_with()
    assert ctx.bot.send_message.await_args == expected


def test_reminder_replaces_pending_job_and_resends_current_status(data, monkeypatch):
    h, ctx = handlers(data), context()
    app = build_application(h.config)
    ctx.job_queue = app.job_queue
    handler, = [handler for handler in app.handlers[0] if isinstance(handler, CallbackQueryHandler)]
    first, second, other = callback(9, REMIND), callback(9, REMIND), callback(10, REMIND)
    # UTC times straddle the spring clock change when two elapsed hours are added.
    times = iter([datetime(2027, 3, 14, 9, 30, tzinfo=UTC),
                  datetime(2027, 3, 14, 9, 40, tzinfo=UTC),
                  datetime(2027, 3, 14, 9, 40, tzinfo=UTC)])
    monkeypatch.setattr("farm.bot.buttons.datetime", SimpleNamespace(now=lambda tz: next(times)))

    async def schedule():
        # Start only the scheduler, paused so no job dispatches. No Telegram bot is started.
        ctx.job_queue.scheduler.start(paused=True)
        try:
            await handler.callback(first, ctx)
            original, = [job for job in ctx.job_queue.jobs() if job.chat_id == 9]
            await handler.callback(other, ctx)
            await handler.callback(second, ctx)
            jobs = [job for job in ctx.job_queue.jobs() if job.chat_id is not None]
            assert sorted(job.chat_id for job in jobs) == [9, 10]
            reminder, = [job for job in jobs if job.chat_id == 9]
            assert reminder is not original
            assert reminder.next_t - original.next_t == timedelta(minutes=10)
            assert reminder.next_t == datetime(2027, 3, 14, 11, 40, tzinfo=UTC)
            ctx.bot.send_message.assert_awaited_with(9, "OK, I'll send it again at 4:40 AM.")
            add_scan(data, ["ripe"])
            await reminder.callback(SimpleNamespace(bot=ctx.bot, job=reminder))
            assert ctx.bot.send_message.await_args.args[0] == 9
            assert "1 ready to pick" in ctx.bot.send_message.await_args.args[1]
            assert "Remind me in 2 h" in buttons(ctx.bot.send_message.await_args)
        finally:
            await ctx.job_queue.stop()

    run(schedule())
    for u in (first, second, other):
        u.callback_query.answer.assert_awaited_once_with()


@pytest.mark.parametrize("chat_id", [22, None])
def test_disallowed_callback_is_acknowledged_without_running_action(data, chat_id):
    h, ctx = handlers(data, allowed="9"), context()
    u = callback(chat_id, REMIND)
    if chat_id is None:
        u.effective_chat = None
    run(StatusButtons(h).handle(u, ctx))
    u.callback_query.answer.assert_awaited_once_with()
    ctx.bot.send_message.assert_not_awaited()


@pytest.mark.parametrize("action", ["v1:mold:old-message", "v1:unknown", None])
def test_unknown_callback_points_to_status(data, action):
    ctx, u = context(), callback(9, action)
    run(StatusButtons(handlers(data)).handle(u, ctx))
    u.callback_query.answer.assert_awaited_once_with()
    assert "Send /status" in ctx.bot.send_message.await_args.args[1]


def test_callback_failure_is_logged_and_replied_to(data, caplog):
    ctx, u = context(), callback(9, WATER)
    u.callback_query.answer.side_effect = BadRequest("Query is too old")
    run(StatusButtons(handlers(data)).handle(u, ctx))
    ctx.bot.send_message.assert_awaited_once_with(9, "I couldn't use that button. Try /status.")
    assert "Could not handle a status button" in caplog.text


def test_callback_swallows_failure_to_send_error_reply(data, caplog):
    ctx, u = context(), callback(9, WATER)
    ctx.bot.send_message.side_effect = Forbidden("bot was blocked by the user")
    run(StatusButtons(handlers(data)).handle(u, ctx))
    u.callback_query.answer.assert_awaited_once_with()
    assert "Could not report a status button error" in caplog.text
