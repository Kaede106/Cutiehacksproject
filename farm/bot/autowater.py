"""Watering from the bot: /water_now with a confirm button, automatic mode, and results.

The bot only queues commands (farm/irrigation_control.py has the queue and every
safety rule); the sensor bridge sends them to the board. This module tells the
grower what happened, and logs each confirmed watering as "watered" in the
harvest log so /week shows it.

Settings (farm/bot/.env): AUTO_WATER (off unless 1), WATER_SECONDS,
MAX_WATER_SECONDS, WATER_COOLDOWN_MIN, MAX_WATERINGS_PER_DAY, WET_ENOUGH_PCT,
AUTO_WATER_EVERY_MIN. See farm/bot/README.md "Watering the grove".
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, ContextTypes

from farm import irrigation_control as ic
from farm.common import store

from . import harvest
from .access import is_allowed
from .config import ConfigError
from .irrigation import WATER_TODAY

if TYPE_CHECKING:
    from .app import Handlers

log = logging.getLogger("farm.bot.water")

PREFIX = "v1:wn:"
CANCEL = PREFIX + "no"
CONFIRM_RE = re.compile(r"^v1:wn:go:(\d{1,2}):([01]):(\d{1,12})$")
CONFIRM_TTL_S = 300  # a confirm button older than this does nothing
STALE_PENDING_S = ic.COMMAND_TTL.total_seconds() + 30  # no result by then: the bridge is not running
SNIPPET = "farm/sensors/arduino/WATER_SNIPPET.md"
NOT_ALLOWED = ("Watering from Telegram needs ALLOWED_CHAT_IDS in farm/bot/.env, so that people who "
               "find the bot can't run the pump. /water still gives advice.")


def confirm_keyboard(seconds: int, override: bool, now: float) -> InlineKeyboardMarkup:
    label = f"Water anyway ({seconds} s)" if override else f"Water {seconds} s"
    go = f"{PREFIX}go:{seconds}:{int(override)}:{int(now)}"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=go),
                                  InlineKeyboardButton("Cancel", callback_data=CANCEL)]])


def requested_seconds(args: list[str] | None) -> int | None | str:
    """The optional seconds argument of /water_now: an int, None (not given), or an error message."""
    if not args:
        return None
    if len(args) == 1 and re.fullmatch(r"\d{1,3}", args[0]) and int(args[0]) > 0:
        return int(args[0])
    return "Use /water_now on its own, or with a number of seconds, for example /water_now 8."


def load_settings() -> ic.WaterSettings:
    """The watering settings from the environment. A wrong value raises ConfigError."""
    try:
        return ic.settings_from_env(os.environ)
    except ic.SettingsError as exc:
        raise ConfigError(str(exc)) from None


class AutoWater:
    def __init__(self, handlers: Handlers, advice: Callable[..., Any],
                 settings: ic.WaterSettings | None = None) -> None:
        """`advice(config, now)` returns the irrigation Advice (app.water_advice; blocking)."""
        self.handlers = handlers
        self.advice = advice
        self.settings = settings or load_settings()
        self._seen_results: int | None = None  # results file length at the first check
        self._stale_told: set[str] = set()

    # ------------------------------------------------------------ wiring

    def register(self, app: Application, unedited: Any) -> None:
        """Handlers and jobs. Call before the catch-all command handler."""
        # Group -1 runs before the status buttons' catch-all handler in group 0.
        app.add_handler(CallbackQueryHandler(self._button_only, pattern=r"^v1:wn:"), group=-1)
        app.add_handler(CommandHandler("water_now", self.water_now, filters=unedited))
        app.job_queue.run_repeating(self.watch_results, interval=3, first=3, name="water-results")
        s = self.settings
        if s.auto:
            app.job_queue.run_repeating(self.auto_check, interval=s.check_every_min * 60, first=60,
                                        name="auto-water")
            log.info("Automatic watering is ON: every %g min, %d s per run, at most %d a day, "
                     "%g min apart, never above %g%% soil moisture.", s.check_every_min, s.seconds,
                     s.max_per_day, s.cooldown_min, s.wet_enough_pct)
        else:
            log.info("Automatic watering is off (AUTO_WATER=0). /water_now still works.")

    def _now(self) -> datetime:
        return datetime.now(self.handlers.config.timezone)

    def _may_water(self, chat_id: int | None) -> bool:
        allowed = self.handlers.config.allowed_chat_ids
        return allowed is not None and chat_id in allowed

    def _subscribers(self) -> list[int]:
        allowed = self.handlers.config.allowed_chat_ids
        return [c for c in self.handlers.state.chats() if is_allowed(c, allowed)]

    # ------------------------------------------------------------ /water_now

    async def water_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.handlers._allowed(update):
            return
        message = update.effective_message
        if not self._may_water(update.effective_chat.id):
            await message.reply_text(NOT_ALLOWED)
            return
        seconds = requested_seconds(getattr(context, "args", None))
        if isinstance(seconds, str):
            await message.reply_text(seconds)
            return
        decision = await asyncio.to_thread(self._check, seconds, False)
        if not decision.allowed and not decision.needs_override:
            await message.reply_text(f"I can't water now. {decision.reason}")
            return
        capped = ""
        if seconds is not None and seconds > decision.seconds:
            capped = f" (the most allowed is {self.settings.max_seconds} s, MAX_WATER_SECONDS)"
        if decision.needs_override:
            text = f"{decision.reason} Water for {decision.seconds} s{capped} anyway?"
        else:
            text = (f"Water the grove for {decision.seconds} s{capped} now? Soil is at "
                    f"{decision.soil_pct:.0f}%{' (simulated)' if decision.soil_simulated else ''}.")
        markup = confirm_keyboard(decision.seconds, decision.needs_override, time.time())
        await message.reply_text(text, reply_markup=markup)

    def _check(self, seconds: int | None, override: bool) -> ic.Decision:
        now = self._now()
        history = ic.statuses(ic.read_commands(), ic.read_results())
        return ic.check(self.settings, now=now, soil=store.latest_sensors(max_age=None), history=history,
                        seconds=seconds, manual=True, override=override)

    async def _button_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.button(update, context)
        raise ApplicationHandlerStop  # the status buttons' handler must not see this button too

    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        chat_id = update.effective_chat.id if self.handlers._allowed(update) else None
        try:
            await query.answer()
            if chat_id is None:
                return
            if not self._may_water(chat_id):
                await self._edit(query, context, chat_id, NOT_ALLOWED)
                return
            if query.data == CANCEL:
                await self._edit(query, context, chat_id, "Cancelled. Nothing was sent to the pump.")
                return
            match = CONFIRM_RE.match(query.data or "")
            if match is None or time.time() - int(match[3]) > CONFIRM_TTL_S:
                await self._edit(query, context, chat_id, "That button has expired. Send /water_now again.")
                return
            seconds, override = int(match[1]), match[2] == "1"
            decision, command = await asyncio.to_thread(
                ic.request, self.settings, now=self._now(), requested_by=f"chat:{chat_id}",
                reason="", seconds=seconds, manual=True, override=override)
            if command is None:
                extra = " Send /water_now to see the choice again." if decision.needs_override else ""
                await self._edit(query, context, chat_id, f"Nothing was sent. {decision.reason}{extra}")
                return
            log.info("Manual watering %s for %d s queued by chat %s.", command["id"], command["seconds"], chat_id)
            await self._edit(query, context, chat_id,
                             f"{decision.reason} Queued for the board; I'll tell you when it confirms.")
        except Exception:
            log.exception("Could not handle a watering button in chat %s", chat_id)
            if chat_id is not None:
                await self._say(context.bot, chat_id, "I couldn't queue the watering. Check the bot's window.")

    async def _edit(self, query: Any, context: Any, chat_id: int, text: str) -> None:
        """Replace the question (and its buttons) with the outcome; send it if that fails."""
        try:
            await query.edit_message_text(text)
        except Exception:
            await context.bot.send_message(chat_id, text)

    # ------------------------------------------------------------ automatic mode

    async def auto_check(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Every AUTO_WATER_EVERY_MIN: if the advice is "water today" and the rules allow, water."""
        if not self.settings.auto:
            return
        try:
            now = self._now()
            advice = await asyncio.to_thread(self.advice, self.handlers.config, now)
            if advice.cadence != WATER_TODAY:
                return
            decision, command = await asyncio.to_thread(
                ic.request, self.settings, now=now, requested_by="auto", reason=advice.reason)
            if command is None:
                log.info("Automatic watering skipped: %s", decision.reason)
                return
            log.info("Automatic watering %s for %d s queued.", command["id"], command["seconds"])
            text = f"Watering now for {decision.seconds} s: soil at {decision.soil_pct:.0f}%"
            text += " (simulated)." if decision.soil_simulated else "."
            for chat_id in self._subscribers():
                await self._say(context.bot, chat_id, text)
        except Exception:
            log.exception("Automatic watering check failed")

    # ------------------------------------------------------------ results

    async def watch_results(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Tell people what the bridge did with each command, and log confirmed waterings."""
        try:
            commands, results = await asyncio.to_thread(lambda: (ic.read_commands(), ic.read_results()))
            if self._seen_results is None:
                self._seen_results = len(results)  # results from before this start were already handled
                self._stale_told = {c["id"] for c in commands if isinstance(c.get("id"), str)}
                return
            new, self._seen_results = results[self._seen_results:], len(results)
            by_id = {c.get("id"): c for c in commands}
            now = self._now()
            for result in new:
                command = by_id.get(result.get("command_id"))
                if command is not None:
                    await self._report(context.bot, command, result, now)
            for item in ic.statuses(commands, results):
                taken = ic.parse_time(item.get("taken_at"))
                if (item["status"] == ic.PENDING and item["id"] not in self._stale_told and taken
                        and (now - taken).total_seconds() > STALE_PENDING_S):
                    self._stale_told.add(item["id"])
                    await self._tell(context.bot, item, "The watering wasn't sent: the sensor bridge isn't "
                                     "answering. Is python -m farm running with the board plugged in?")
        except Exception:
            log.exception("Could not check the watering results")

    async def _report(self, bot: Any, command: dict, result: dict, now: datetime) -> None:
        status, seconds = result.get("status"), result.get("seconds") or command.get("seconds")
        simulated = result.get("simulated") is True
        if status == ic.DONE:
            if simulated:
                text = (f"Simulated watering for {seconds} s done. No board is connected, "
                        "so no water really ran.")
            else:
                text = f"Done: watered for {seconds} s. The board confirmed it."
            await asyncio.to_thread(self._log_watered, command, seconds, simulated, now)
        elif status == ic.NO_ACK:
            text = (f"I sent the {seconds} s watering to the board, but it didn't confirm. Check the pump, "
                    f"and that the board has the watering code ({SNIPPET}). I haven't logged it as watered.")
        elif status == ic.FAILED:
            text = f"The watering didn't run: {result.get('detail') or 'unknown error'}."
        elif status == ic.EXPIRED:
            if command.get("id") in self._stale_told:
                return
            text = "The watering didn't run: the sensor bridge picked it up too late, so it skipped it."
        else:
            return  # "sent": wait for the board's answer
        self._stale_told.add(command.get("id"))
        await self._tell(bot, command, text)

    def _log_watered(self, command: dict, seconds: Any, simulated: bool, now: datetime) -> None:
        source = "auto" if command.get("requested_by") == "auto" else "/water_now"
        text = f"{'simulated ' if simulated else ''}{source} {seconds} s"
        for chat_id in self._chats_for(command):
            try:
                harvest.append_entry(chat_id, "watered", 1, text, demo=simulated, now=now)
            except harvest.WriteLimitReached:
                log.info("Not logging watering %s for chat %s: harvest log limit.", command.get("id"), chat_id)

    def _chats_for(self, command: dict) -> list[int]:
        by = command.get("requested_by")
        if isinstance(by, str) and by.startswith("chat:"):
            try:
                return [int(by[5:])]
            except ValueError:
                return []
        return self._subscribers()

    async def _tell(self, bot: Any, command: dict, text: str) -> None:
        for chat_id in self._chats_for(command):
            await self._say(bot, chat_id, text)

    async def _say(self, bot: Any, chat_id: int, text: str) -> None:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            log.exception("Could not send a watering message to chat %s", chat_id)
