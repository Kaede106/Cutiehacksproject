"""Inline actions for status messages and their one-off reminders."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from farm.common import store

from .access import is_allowed, photo_path
from .compose import Photo, compose

if TYPE_CHECKING:
    from .app import Handlers

log = logging.getLogger(__name__)
WATER = "v1:water"
MOLD_PREFIX = "v1:mold:"
REMIND = "v1:remind"
REMINDER_DELAY = timedelta(hours=2)


def photo_paths(data_dir: Path, photos: tuple[Photo, ...]) -> list[tuple[Path, str]]:
    paths = [(photo_path(data_dir, photo.path), photo.caption) for photo in photos]
    return [(path, caption) for path, caption in paths if path is not None]


def _mold_callback(paths: list[tuple[Path, str]]) -> str:
    # Identify the photo set without exposing any file paths or storing messages in memory.
    payload = json.dumps([(str(path), caption) for path, caption in paths])
    return MOLD_PREFIX + hashlib.sha256(payload.encode()).hexdigest()[:24]


def status_keyboard(paths: list[tuple[Path, str]]) -> InlineKeyboardMarkup:
    actions = [InlineKeyboardButton("Watering details", callback_data=WATER)]
    if paths:
        actions.append(InlineKeyboardButton("Mold photos", callback_data=_mold_callback(paths)))
    return InlineKeyboardMarkup([actions, [InlineKeyboardButton("Remind me in 2 h", callback_data=REMIND)]])


async def send_photos(bot: Bot, chat_id: int, paths: list[tuple[Path, str]]) -> None:
    if len(paths) == 1:
        path, caption = paths[0]
        await bot.send_photo(chat_id, photo=path, caption=caption, parse_mode=ParseMode.HTML)
    else:
        media = [InputMediaPhoto(media=path, caption=caption, parse_mode=ParseMode.HTML)
                 for path, caption in paths]
        await bot.send_media_group(chat_id, media=media)


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
            elif isinstance(action, str) and action.startswith(MOLD_PREFIX):
                await self._resend_mold(context.bot, chat_id, action)
            else:
                await context.bot.send_message(chat_id, "That button is out of date. Send /status for new buttons.")
        except Exception:
            log.exception("Could not handle a status button in chat %s", chat_id)
            if chat_id is not None:
                await self._reply_error(context.bot, chat_id, "I couldn't use that button. Try /status.")

    def _current_mold_paths(self) -> list[tuple[Path, str]]:
        data = store.data_dir()
        scan = store.latest_scan(max_age=None)
        now = datetime.now(self.handlers.config.timezone)
        message = compose(scan, None, now, photo_ok=lambda rel: photo_path(data, rel) is not None)
        return photo_paths(data, message.photos)

    async def _resend_mold(self, bot: Bot, chat_id: int, action: str) -> None:
        paths = await asyncio.to_thread(self._current_mold_paths)
        if not paths or action != _mold_callback(paths):
            await bot.send_message(chat_id, "Those mold photos are no longer available. Send /status for the latest scan.")
            return
        await send_photos(bot, chat_id, paths)

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
