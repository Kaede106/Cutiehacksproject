"""The few settings the dashboard needs, read the way the bot reads them.

`farm/bot/.env` also holds secrets (the Telegram token, an OpenAI key). The dashboard never
needs them, so only the keys below are copied from that file into the environment, and the
rest of the file is never looked at. Real environment variables win, as in the bot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from zoneinfo import ZoneInfo

from farm.bot.config import DEFAULT_TIMEZONE, ENV_FILE, ConfigError, parse_irrigation, parse_timezone
from farm.bot.irrigation import IrrigationConfig

ALLOWED_KEYS = (
    "CUTIEFARM_DATA", "TIMEZONE", "FARM_LAT", "FARM_LON", "WATER_BELOW_PCT", "CITRUS_KC",
    "HOLD_OFF_BELOW_MM", "WEEKLY_FROM_MM", "TWICE_WEEKLY_FROM_MM",
)


@dataclass(frozen=True)
class Settings:
    irrigation: IrrigationConfig
    timezone: ZoneInfo
    warnings: tuple[str, ...] = ()


def load_env_file() -> None:
    """Copy the allowed keys from farm/bot/.env into os.environ (real variables win)."""
    if not ENV_FILE.is_file():
        return
    try:
        from dotenv import dotenv_values
        values = dotenv_values(ENV_FILE)
    except Exception:  # a missing package or an unreadable file: run on the defaults
        return
    for key in ALLOWED_KEYS:
        value = values.get(key)
        if value and key not in os.environ:
            os.environ[key] = value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Irrigation thresholds and time zone. A bad value falls back to the default, with a warning."""
    env = os.environ if env is None else env
    warnings: list[str] = []
    try:
        irrigation = parse_irrigation(env)
    except ConfigError as exc:
        irrigation = IrrigationConfig()
        warnings.append(f"{exc} Using the default watering settings.")
    try:
        tz = parse_timezone(env.get("TIMEZONE") or DEFAULT_TIMEZONE)
    except ConfigError as exc:
        tz = parse_timezone(DEFAULT_TIMEZONE)
        warnings.append(f"{exc} Using {DEFAULT_TIMEZONE}.")
    return Settings(irrigation, tz, tuple(warnings))
