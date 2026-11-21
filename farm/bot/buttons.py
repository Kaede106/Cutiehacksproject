"""Inline actions for status messages and their one-off reminders."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


from .access import is_allowed

if TYPE_CHECKING:
    from .app import Handlers

log = logging.getLogger(__name__)
WATER = "v1:water"
REMIND = "v1:remind"
REMINDER_DELAY = timedelta(hours=2)


def status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Watering details", callback_data=WATER)],
        [InlineKeyboardButton("Remind me in 2 h", callback_data=REMIND)],
    ])


class StatusButtons:
    def __init__(self, handlers: Handlers) -> None:
        self.handlers = handlers

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        chat_id = update.effective_chat.id if self.handlers._allowed(update) else None
        try:
            await query.answer()
            if chat_id is None:
                return
            action = query.data
            if action == WATER:
                await self.handlers.water(update, context)
            elif action == REMIND:
                when = self._schedule_reminder(context, chat_id)
                await context.bot.send_message(chat_id, f"OK, I'll send it again at {when}.")
            else:
                await context.bot.send_message(chat_id, "That button is out of date. Send /status for new buttons.")
        except Exception:
            log.exception("Could not handle a status button in chat %s", chat_id)
            if chat_id is not None:
                await self._reply_error(context.bot, chat_id, "I couldn't use that button. Try /status.")

    def _schedule_reminder(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
        due = datetime.now(UTC) + REMINDER_DELAY
        name = f"status-reminder:{chat_id}"
        context.job_queue.run_once(self._send_reminder, due, chat_id=chat_id, name=name,
                                   job_kwargs={"id": name, "replace_existing": True})
        return due.astimezone(self.handlers.config.timezone).strftime("%I:%M %p").lstrip("0")

    async def _send_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.chat_id
        if not is_allowed(chat_id, self.handlers.config.allowed_chat_ids):
            return
        try:
            await self.handlers._send_current(context.bot, chat_id)
        except Exception:
            log.exception("Could not send the status reminder to chat %s", chat_id)
            await self._reply_error(context.bot, chat_id, "I couldn't send the status reminder. Try /status.")

    async def _reply_error(self, bot: Bot, chat_id: int, text: str) -> None:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            log.exception("Could not report a status button error to chat %s", chat_id)
