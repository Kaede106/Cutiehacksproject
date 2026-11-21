"""Telegram side: commands, the daily job, and sending a composed message."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import BotCommand, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from farm.common import store

from .access import is_allowed, photo_path
from .chat import Conversation, farm_context, keyword_intent, strip_html
from .compose import Message, Photo, _mold_photos, compose
from .photo import classify_photo, photo_reply
from .config import Config
from .irrigation import Advice, advise, water_message
from .state import STATE_FILE, State
from .weather import get_weather

log = logging.getLogger("farm.bot")

COMMANDS = [
    ("status", "Get today's message now"),
    ("water", "Watering advice and what it is based on"),
    ("start", "Get the message every morning"),
    ("stop", "Stop the morning message"),
    ("help", "What this bot does"),
]
COMMANDS_LINE = "I understand /status, /water, /start, /stop and /help."
MAX_HISTORY = 20_000  # sensor readings kept in memory; a week at one a minute is about 10,000


def clock(t) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def sensor_history() -> list[dict]:
    """Every sensor reading, oldest first (only the newest MAX_HISTORY).

    store.py has no public history reader yet, only latest_sensors(). This is the
    one place that uses its private _read, so it is a one-line change once a
    public store.sensor_history() exists.
    """
    return list(deque(store._read(store.SENSORS_FILE), maxlen=MAX_HISTORY))


def water_advice(config: Config, now: datetime | None = None) -> Advice:
    """Watering advice from the sensor history and, if FARM_LAT/FARM_LON are set, the forecast.
    Blocking (it may call Open-Meteo once a day): run it in a thread from async code."""
    now = now or datetime.now(config.timezone)
    irr = config.irrigation
    weather = get_weather(irr.latitude, irr.longitude, config.timezone.key, now.date(), store.data_dir())
    return advise(sensor_history(), weather, now.date(), irr, now=now)


def build_message(config: Config, now: datetime | None = None) -> Message:
    """Read the latest records through the store and compose the message. Blocking."""
    data = store.data_dir()
    now = now or datetime.now(config.timezone)
    return compose(
        store.latest_scan(max_age=None),
        store.latest_sensors(max_age=None),
        now,
        photo_ok=lambda rel: photo_path(data, rel) is not None,
        scan_command=config.scan_command,
        irrigation=_advice_or_none(config, now),
    )


def _advice_or_none(config: Config, now: datetime) -> Advice | None:
    try:
        return water_advice(config, now)
    except Exception:
        log.exception("Could not work out the watering advice")
        return None


async def send(bot: Any, chat_id: int, message: Message, data_dir: Path) -> None:
    await bot.send_message(chat_id, message.text, parse_mode=ParseMode.HTML)
    paths = [(photo_path(data_dir, p.path), p.caption) for p in message.photos]
    paths = [(path, caption) for path, caption in paths if path is not None]
    if not paths:
        return
    try:
        if len(paths) == 1:
            path, caption = paths[0]
            await bot.send_photo(chat_id, photo=path, caption=caption, parse_mode=ParseMode.HTML)
        else:
            media = [InputMediaPhoto(media=path, caption=caption, parse_mode=ParseMode.HTML)
                     for path, caption in paths]
            await bot.send_media_group(chat_id, media=media)
    except Forbidden:
        raise
    except (TelegramError, OSError):
        log.exception("Could not send the mold photo to chat %s", chat_id)
        await bot.send_message(chat_id, "I could not send the photo. It is in the data folder on the laptop.")


class Handlers:
    def __init__(self, config: Config, state: State, conversation: Conversation | None = None) -> None:
        self.config = config
        self.state = state
        self.conversation = conversation or Conversation()
        self._last_scan_id: str | None = None  # for instant mold alerts; set on the first check

    def _allowed(self, update: Update) -> bool:
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        if is_allowed(chat_id, self.config.allowed_chat_ids):
            return True
        log.info("Ignored a message from chat %s (not in ALLOWED_CHAT_IDS).", chat_id)
        return False

    def _daily(self) -> str:
        return f"{clock(self.config.daily_at)} ({self.config.timezone.key})"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        new = self.state.subscribe(chat_id, datetime.now(self.config.timezone))
        first = "You are subscribed." if new else "You were already subscribed."
        text = (f"{first} I will send the state of your oranges every day at {self._daily()}. "
                "Send /status to get it now, or /stop to unsubscribe.")
        # People who arrive from the landing page's button (t.me/<bot>?start=landing) are visitors,
        # not the owner, so they don't get the owner's set-up hint.
        args = getattr(context, "args", None) or []
        from_landing = bool(args) and args[0] == "landing"
        if self.config.allowed_chat_ids is None and not from_landing:
            text += (f"\n\nAnyone can use this bot right now. Your chat ID is {chat_id}: put "
                     f"ALLOWED_CHAT_IDS={chat_id} in farm/bot/.env and restart the bot to keep others out.")
        await update.effective_message.reply_text(text)
        # Show today's state straight away, so subscribing is visibly in sync with the farm.
        if new:
            await self._send_current(context.bot, chat_id)

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.state.unsubscribe(update.effective_chat.id):
            text = "You are unsubscribed and will not get the morning message. Send /start to subscribe again."
        else:
            text = "You were not subscribed. Send /start to get the morning message."
        await update.effective_message.reply_text(text)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await self._send_current(context.bot, update.effective_chat.id)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        lines = [
            "CutieFarm watches your oranges with a camera and tells you what to do.",
            "",
            "/status: what to do today, right now",
            "/water: watering advice and what it is based on",
            f"/start: get it every day at {self._daily()}",
            "/stop: stop the daily message",
            "/help: this message",
        ]
        await update.effective_message.reply_text("\n".join(lines))

    async def text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        question = (update.effective_message.text or "").strip()
        chat_id = update.effective_chat.id
        now = datetime.now(self.config.timezone)
        if question and self.conversation.enabled:
            try:
                await context.bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            facts = await asyncio.to_thread(self._farm_context, now)
            answer = await self.conversation.reply(chat_id, question, facts, now.date())
            if answer:
                await update.effective_message.reply_text(answer)
                return
        intent = keyword_intent(question)
        if intent == "status":
            await self._send_current(context.bot, chat_id)
        elif intent == "water":
            await self.water(update, context)
        elif intent == "help":
            await self.help(update, context)
        else:
            await update.effective_message.reply_text(
                "Ask me about your oranges or about watering, or use " + COMMANDS_LINE[len("I understand "):])

    async def photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Someone sent a photo: run the colour check on its centre, on this laptop."""
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        message = update.effective_message
        try:
            await context.bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        try:
            file = await message.photo[-1].get_file()
            data = bytes(await file.download_as_bytearray())
            result = await asyncio.to_thread(classify_photo, data)
        except Exception:
            log.exception("Could not check a photo from chat %s", chat_id)
            await message.reply_text("I couldn't read that photo. Try sending it again as a normal photo, not a file.")
            return
        reply = photo_reply(result)
        now = datetime.now(self.config.timezone)
        worded = await self.conversation.reword(chat_id, reply, message.caption or "", now.date())
        await message.reply_text(worded or reply)

    async def watch_scans(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Instant alert: when a new scan has possible mold, tell subscribers now, not at 9:00."""
        try:
            scan = await asyncio.to_thread(store.latest_scan, None)
        except Exception:
            log.exception("Could not read the latest scan for mold alerts")
            return
        if not scan:
            return
        scan_id = str(scan.get("id") or scan.get("taken_at"))
        if self._last_scan_id is None or scan_id == self._last_scan_id:
            self._last_scan_id = scan_id  # the first check only sets the baseline
            return
        self._last_scan_id = scan_id
        message = mold_alert(scan, store.data_dir())
        if message is None:
            return
        chats = [c for c in self.state.chats() if is_allowed(c, self.config.allowed_chat_ids)]
        log.info("Mold alert for scan %s: sending to %d chat(s).", scan_id, len(chats))
        for chat_id in chats:
            try:
                await send(context.bot, chat_id, message, store.data_dir())
            except Forbidden:
                self.state.unsubscribe(chat_id)
            except TelegramError:
                log.exception("Could not send the mold alert to chat %s", chat_id)

    def _farm_context(self, now: datetime) -> str:
        scan = store.latest_scan(max_age=None)
        sensors = store.latest_sensors(max_age=None)
        try:
            watering = strip_html(water_message(water_advice(self.config, now), now.date()))
        except Exception:
            log.exception("Could not work out the watering advice for a chat answer")
            watering = None
        return farm_context(scan, sensors, watering, now)

    async def water(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        now = datetime.now(self.config.timezone)
        try:
            advice = await asyncio.to_thread(water_advice, self.config, now)
            text = water_message(advice, now.date())
        except Exception:
            log.exception("Could not work out the watering advice")
            text = "I could not work out the watering advice. Check the bot's window for the error."
        await context.bot.send_message(update.effective_chat.id, text, parse_mode=ParseMode.HTML)

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.effective_message.reply_text(COMMANDS_LINE)

    async def daily(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chats = [c for c in self.state.chats() if is_allowed(c, self.config.allowed_chat_ids)]
        log.info("Daily message: sending to %d chat(s).", len(chats))
        if not chats:
            return
        message = await self._message_or_error()
        data = store.data_dir()
        for chat_id in chats:
            try:
                await send(context.bot, chat_id, message, data)
            except Forbidden:
                log.info("Chat %s blocked the bot; unsubscribing it.", chat_id)
                self.state.unsubscribe(chat_id)
            except TelegramError:
                log.exception("Could not send the daily message to chat %s", chat_id)

    async def _send_current(self, bot: Any, chat_id: int) -> None:
        await send(bot, chat_id, await self._message_or_error(), store.data_dir())

    async def _message_or_error(self) -> Message:
        try:
            return await asyncio.to_thread(build_message, self.config)
        except Exception:
            log.exception("Could not compose the message")
            return Message("I could not read today's scan on the laptop. Check the bot's window for the error.")


def mold_alert(scan: dict, data_dir: Path) -> Message | None:
    """The instant alert for a scan with possible mold, or None if it has none."""
    molds = [f for f in scan.get("fruits") or [] if f.get("label") == "mold"]
    if not molds:
        return None
    try:
        taken = clock(datetime.fromisoformat(scan["taken_at"]).timetz())
    except Exception:
        taken = "the latest scan"
    count = "1 orange" if len(molds) == 1 else f"{len(molds)} oranges"
    lines = [f"<b>Possible mold spotted</b> on {count} in the scan at {taken}. Remove "
             f"{'it' if len(molds) == 1 else 'them'} before the mold spreads."]
    if scan.get("demo"):
        lines.append("<i>Demo data: the camera isn't connected yet, so this scan is an example.</i>")
    photos = _mold_photos(scan, lambda rel: photo_path(data_dir, rel) is not None)
    return Message("\n".join(lines), tuple(photos))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error while handling an update", exc_info=context.error)


def build_application(config: Config) -> Application:
    state = State(store.data_dir() / STATE_FILE)
    handlers = Handlers(config, state)

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])

    app = Application.builder().token(config.token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("stop", handlers.stop))
    app.add_handler(CommandHandler("status", handlers.status))
    app.add_handler(CommandHandler("help", handlers.help))
    app.add_handler(CommandHandler("water", handlers.water))
    app.add_handler(MessageHandler(filters.COMMAND, handlers.unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.photo))
    app.add_error_handler(on_error)
    app.job_queue.run_daily(handlers.daily, time=config.daily_at, name="daily-message")
    app.job_queue.run_repeating(handlers.watch_scans, interval=30, first=5, name="mold-alerts")
    return app
