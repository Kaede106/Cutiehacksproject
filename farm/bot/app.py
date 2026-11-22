"""Telegram side: commands, the daily job, and sending a composed message."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import BotCommand, PhotoSize, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from farm.common import store

from . import harvest
from .access import is_allowed, photo_path
from .autowater import AutoWater
from .buttons import StatusButtons, status_keyboard
from .chat import LIMIT_NOTICE, LIMITS_FILE, Conversation, LimitReached, farm_context, keyword_intent, strip_html
from .compose import Message, Photo, _counts, compose, health_line, sick_fruits
from .forecast import Forecast, forecast_harvest
from .photo import classify_photo, photo_reply
from .config import Config
from .irrigation import Advice, advise, water_message
from .state import STATE_FILE, State
from .voice import MAX_AUDIO_BYTES, too_large, too_long
from .weather import get_weather

log = logging.getLogger("farm.bot")

COMMANDS = [
    ("status", "See what is ready to pick and when to water"),
    ("water", "Watering advice and what it is based on"),
    ("water_now", "Water the grove now, after a safety check"),
    ("picked", "Log oranges picked, for example /picked 3"),
    ("watered", "Log that you watered today"),
    ("undo", "Undo this chat's last harvest log entry"),
    ("week", "Show the last 7 days of scans and harvest activity"),
    ("start", "Get the message every morning"),
    ("stop", "Stop the morning message"),
    ("help", "What this bot does"),
]
COMMANDS_LINE = "I understand " + ", ".join(f"/{command}" for command, _ in COMMANDS[:-1]) + " and /help."
MAX_HISTORY = 20_000  # sensor readings kept in memory; a week at one a minute is about 10,000
MAX_PHOTO_BYTES = 5_000_000


def clock(t) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def sensor_history() -> list[dict]:
    """Every sensor reading, oldest first (only the newest MAX_HISTORY).

    store.py has no public sensor history reader yet, only latest_sensors().
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
    now = now or datetime.now(config.timezone)
    return compose(
        store.latest_scan(max_age=None),
        store.latest_sensors(max_age=None),
        now,
        scan_command=config.scan_command,
        irrigation=_advice_or_none(config, now),
        forecast=_forecast_or_none(now),
    )


def _advice_or_none(config: Config, now: datetime) -> Advice | None:
    try:
        return water_advice(config, now)
    except Exception:
        log.exception("Could not work out the watering advice")
        return None


def _forecast_or_none(now: datetime) -> Forecast | None:
    try:
        scans = deque(store._read(store.SCANS_FILE), maxlen=MAX_HISTORY)
        picks = deque(store._read(harvest.HARVEST_FILE), maxlen=MAX_HISTORY)
        return forecast_harvest(scans, now, picks)
    except Exception:
        log.exception("Could not work out the harvest forecast")
        return None


async def send(bot: Any, chat_id: int, message: Message, data_dir: Path, *, status: bool = True) -> None:
    markup = status_keyboard() if status else None
    await bot.send_message(chat_id, message.text, parse_mode=ParseMode.HTML, reply_markup=markup)
    for photo in message.photos:
        path = photo_path(data_dir, photo.path)
        if path is None:
            continue
        try:
            await bot.send_photo(chat_id, photo=path, caption=photo.caption, parse_mode=ParseMode.HTML)
        except Forbidden:
            raise
        except (TelegramError, OSError):
            log.exception("Could not send the scan photo to chat %s", chat_id)


class Handlers:
    def __init__(self, config: Config, state: State, conversation: Conversation | None = None) -> None:
        self.config = config
        self.state = state
        self.conversation = conversation or Conversation(limits_path=store.data_dir() / LIMITS_FILE)
        self._last_scan_id: str | None = None
        self._last_ripe: int | None = None
        self._checked_scans = False
        self._started_empty = False

    def _allowed(self, update: Update) -> bool:
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        if self.config.allowed_chat_ids is None and chat and chat.type != ChatType.PRIVATE:
            return False
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
        text = (f"{first} I will send ripeness and watering advice every day at {self._daily()}. "
                "I will also alert you when more oranges are ready to pick. Send /status for the latest advice.")
        if self.config.allowed_chat_ids is None:
            log.info("Anyone can use this bot in a private chat. /start came from chat %s. "
                     "Set ALLOWED_CHAT_IDS=%s in farm/bot/.env and restart the bot to restrict access.",
                     chat_id, chat_id)
        await update.effective_message.reply_text(text)
        # Show today's state straight away, so subscribing is visibly in sync with the farm.
        if new:
            await self._send_current(context.bot, chat_id)

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.state.unsubscribe(update.effective_chat.id):
            text = "You are unsubscribed and will not get the morning message or alerts. Send /start to subscribe again."
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
            "CutieFarm checks which oranges are ready to pick and when to water the grove.",
            "",
            "/status: what is ready to pick and when to water",
            "/water: watering advice and what it is based on",
            "/water_now: run the pump now, after a safety check and your OK",
            "/picked 3, /watered: log what you did",
            "/undo: undo this chat's last harvest log entry",
            "/week: see the last 7 days of scans and harvest activity",
            f"/start: get it every day at {self._daily()}",
            "/stop: stop the daily message",
            "/help: this message",
        ]
        await update.effective_message.reply_text("\n".join(lines))

    async def record_harvest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        message = update.effective_message
        now = datetime.now(self.config.timezone)
        if not await harvest.maybe_record(update.effective_chat.id, message, now=now, command=True):
            await message.reply_text("Use /picked 3 with a count from 1 to 10,000, or /watered on its own.")

    async def undo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        now = datetime.now(self.config.timezone)
        try:
            undone = await asyncio.to_thread(harvest.undo, update.effective_chat.id, now=now)
        except harvest.WriteLimitReached:
            await update.effective_message.reply_text(harvest.WRITE_LIMIT_NOTICE)
            return
        await update.effective_message.reply_text(
            "Undid your last harvest log entry." if undone else "No harvest log entry to undo in this chat.")

    async def week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        now = datetime.now(self.config.timezone)
        text = await asyncio.to_thread(harvest.week_summary, update.effective_chat.id, now)
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        now = datetime.now(self.config.timezone)
        if await harvest.maybe_record(update.effective_chat.id, update.effective_message, now=now):
            return
        question = (update.effective_message.text or "").strip()
        await self._answer(update, context, question)

    async def _answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
        chat_id = update.effective_chat.id
        now = datetime.now(self.config.timezone)
        fallback = "CutieFarm only checks ripeness and watering. Try " + COMMANDS_LINE[len("I understand "):]
        if question and self.conversation.enabled:
            try:
                await context.bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            try:
                facts = await asyncio.to_thread(self._farm_context, now)
                answer = await self.conversation.reply(
                    chat_id, question, facts, datetime.now(self.config.timezone).date())
            except LimitReached:
                fallback = LIMIT_NOTICE
            except Exception:
                log.exception("Could not prepare a chat answer")
            else:
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
            await update.effective_message.reply_text(fallback)

    async def voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        message = update.effective_message
        media = message.voice or message.audio
        if too_long(media):
            await message.reply_text("Please send an audio clip of 60 seconds or less, or type your question.")
            return
        if too_large(media):
            await message.reply_text(f"Please send an audio clip of {MAX_AUDIO_BYTES:,} bytes or less, or type your question.")
            return
        if not self.conversation.enabled:
            await message.reply_text("Voice notes and audio need OPENAI_API_KEY. Try /status, /water or /help.")
            return
        now = datetime.now(self.config.timezone)
        if not self.conversation.limits.take(update.effective_chat.id, now.date()):
            await message.reply_text("I've reached today's audio limit. /status and /water still work.")
            return
        question = await self.conversation.transcriber.transcribe(media, is_voice=message.voice is not None)
        if not question:
            await message.reply_text("I couldn't transcribe that audio. Try recording it again or type your question.")
            return
        # Leave room for the quote even if every character takes two UTF-16 code units.
        quote = question if len(question) <= 2000 else question[:2000] + "…"
        await message.reply_text(f'You said: "{quote}"')
        now = datetime.now(self.config.timezone)
        if await harvest.maybe_record(update.effective_chat.id, message, now=now, text=question):
            return
        await self._answer(update, context, question)

    async def photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Someone sent a photo: run the colour check on its centre, on this laptop."""
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        message = update.effective_message

        def area(size: PhotoSize) -> int:
            return size.width * size.height

        suitable = [size for size in message.photo if min(size.width, size.height) >= 256]
        size = min(suitable, key=area) if suitable else max(message.photo, key=area)
        if size.file_size is not None and size.file_size > MAX_PHOTO_BYTES:
            await message.reply_text("Please send a photo of 5 MB or less.")
            return
        try:
            await context.bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        try:
            file = await size.get_file()
            data = bytes(await file.download_as_bytearray())
            if len(data) > MAX_PHOTO_BYTES:
                await message.reply_text("Please send a photo of 5 MB or less.")
                return
            result = await asyncio.to_thread(classify_photo, data)
        except Exception:
            log.exception("Could not check a photo from chat %s", chat_id)
            await message.reply_text("I couldn't read that photo. Try sending it again as a normal photo, not a file.")
            return
        reply = photo_reply(result)
        now = datetime.now(self.config.timezone)
        worded = await self.conversation.reword(chat_id, reply, message.caption or "", now.date())
        await message.reply_text(worded or reply)

    def _pending_scans(self) -> list[dict]:
        """Read scans appended after the baseline, in file order."""
        pending = []
        everything = []
        latest = None
        baseline_found = False
        for scan in store._read(store.SCANS_FILE):
            latest = scan
            everything.append(scan)
            if scan_key(scan) == self._last_scan_id:
                baseline_found = True
                pending.clear()
            elif baseline_found:
                pending.append(scan)
        first_check = not self._checked_scans
        self._checked_scans = True
        if latest is None and first_check:
            self._started_empty = True  # no scans at startup: the first ones to arrive are all new
        if not baseline_found and latest is not None and self._started_empty:
            # The file was empty when the bot started (e.g. a live camera demo): compare with zero ripe.
            self._started_empty = False
            self._last_scan_id, self._last_ripe = None, 0
            return everything
        if not baseline_found:
            # On startup or after the file is replaced, use its latest scan as the baseline.
            self._last_scan_id = scan_key(latest) if latest else None
            self._last_ripe = _counts(latest)["ripe"] if latest else None
        return pending

    async def watch_scans(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Tell subscribers when a new scan shows more ripe oranges."""
        try:
            scans = await asyncio.to_thread(self._pending_scans)
            if not scans:
                return
            data = store.data_dir()
            for scan in scans:
                scan_id = scan_key(scan)
                if scan_id == self._last_scan_id:
                    continue
                ripe = _counts(scan)["ripe"]
                increase = ripe - self._last_ripe if self._last_ripe is not None else 0
                self._last_scan_id, self._last_ripe = scan_id, ripe
                sick = sick_fruits(scan)
                if increase <= 0 and not sick:
                    continue
                message = ripe_alert(scan, increase, ripe, len(sick), health_line(scan) if sick else None)
                chats = [c for c in self.state.chats() if is_allowed(c, self.config.allowed_chat_ids)]
                log.info("Ripe alert for scan %s: sending to %d chat(s).", scan_id, len(chats))
                for chat_id in chats:
                    try:
                        await send(context.bot, chat_id, message, data, status=False)
                    except Forbidden:
                        self.state.unsubscribe(chat_id)
                    except Exception:
                        log.exception("Could not send the ripe alert to chat %s", chat_id)
        except Exception:
            log.exception("Could not check scans for ripe alerts")

    def _farm_context(self, now: datetime) -> str:
        scan = store.latest_scan(max_age=None)
        sensors = store.latest_sensors(max_age=None)
        try:
            watering = strip_html(water_message(water_advice(self.config, now), now.date()))
        except Exception:
            log.exception("Could not work out the watering advice for a chat answer")
            watering = None
        return farm_context(scan, sensors, watering, now, forecast=_forecast_or_none(now))

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


def scan_key(scan: dict) -> str:
    return str(scan.get("id") or scan.get("taken_at"))


def ripe_alert(scan: dict, increase: int, ripe: int, sick: int = 0, sick_text: str | None = None) -> Message:
    parts = []
    if increase > 0:
        fruit = "orange is" if increase == 1 else "oranges are"
        parts.append(f"<b>{increase} more {fruit} ready to pick ({ripe} in total).</b>")
    if sick and sick_text:
        parts.append(sick_text)
    text = "\n".join(parts)
    if scan.get("demo"):
        text += "\n<i>Demo data: this scan is an example.</i>"
    image = scan.get("image")
    photos = (Photo(image, "Latest scan."),) if isinstance(image, str) and image else ()
    return Message(text, photos)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error while handling an update", exc_info=context.error)


def build_application(config: Config) -> Application:
    state = State(store.data_dir() / STATE_FILE)
    handlers = Handlers(config, state)

    async def post_init(app: Application) -> None:
        try:
            await asyncio.to_thread(handlers._pending_scans)
        except Exception:
            log.exception("Could not set the startup baseline for ripe alerts")
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])

    app = Application.builder().token(config.token).post_init(post_init).concurrent_updates(8).build()
    unedited = ~filters.UpdateType.EDITED & ~filters.UpdateType.EDITED_BUSINESS_MESSAGE
    AutoWater(handlers, water_advice).register(app, unedited)  # /water_now, its buttons, auto mode
    app.add_handler(CallbackQueryHandler(StatusButtons(handlers).handle))
    app.add_handler(CommandHandler("start", handlers.start, filters=unedited))
    app.add_handler(CommandHandler("stop", handlers.stop, filters=unedited))
    app.add_handler(CommandHandler("status", handlers.status, filters=unedited))
    app.add_handler(CommandHandler("help", handlers.help, filters=unedited))
    app.add_handler(CommandHandler("water", handlers.water, filters=unedited))
    app.add_handler(CommandHandler(("picked", "watered"), handlers.record_harvest, filters=unedited))
    app.add_handler(CommandHandler("undo", handlers.undo, filters=unedited))
    app.add_handler(CommandHandler("week", handlers.week, filters=unedited))
    app.add_handler(MessageHandler(unedited & filters.COMMAND, handlers.unknown))
    app.add_handler(MessageHandler(unedited & filters.TEXT & ~filters.COMMAND, handlers.text))
    app.add_handler(MessageHandler(unedited & filters.PHOTO, handlers.photo))
    app.add_handler(MessageHandler(unedited & (filters.VOICE | filters.AUDIO), handlers.voice))
    app.add_error_handler(on_error)
    app.job_queue.run_daily(handlers.daily, time=config.daily_at, name="daily-message")
    app.job_queue.run_repeating(handlers.watch_scans, interval=30, first=5, name="ripe-alerts")
    return app
