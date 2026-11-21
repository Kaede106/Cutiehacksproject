"""Bot configuration from the environment and farm/bot/.env. The token is never printed."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .irrigation import IrrigationConfig

BOT_DIR = Path(__file__).resolve().parent
ENV_FILE = BOT_DIR / ".env"

DEFAULT_DAILY_AT = "09:00"
DEFAULT_TIMEZONE = "America/Los_Angeles"

MISSING_TOKEN = (
    "TELEGRAM_BOT_TOKEN is not set. In Telegram, message @BotFather, send /newbot and copy the token it "
    "gives you into farm/bot/.env as TELEGRAM_BOT_TOKEN=<token> (copy farm/bot/.env.example to start)."
)

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_LOG_SECRET_RE = re.compile(r"bot\d{5,}:[A-Za-z0-9_%-]{30,}|sk-[A-Za-z0-9_-]{20,}")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class ConfigError(Exception):
    """A setting is missing or wrong. The message is one line, safe to print."""


class MissingTokenError(ConfigError):
    def __init__(self) -> None:
        super().__init__(MISSING_TOKEN)


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    daily_at: time  # timezone-aware
    timezone: ZoneInfo
    allowed_chat_ids: frozenset[int] | None  # None: anyone may use the bot in a private chat
    scan_command: str | None = None  # how to run a scan by hand, shown in "no scan" messages
    irrigation: IrrigationConfig = IrrigationConfig()


def load_env_file(path: Path = ENV_FILE) -> None:
    """Load farm/bot/.env into os.environ. Real environment variables win."""
    if path.is_file():
        from dotenv import load_dotenv

        load_dotenv(path, override=False)


def parse_daily_at(value: str, tz: ZoneInfo) -> time:
    match = _TIME_RE.match(value.strip())
    if match:
        hour, minute = int(match[1]), int(match[2])
        if hour < 24 and minute < 60:
            return time(hour, minute, tzinfo=tz)
    raise ConfigError(f"DAILY_AT must be a 24-hour time like 09:00 or 18:30, not {value.strip()!r}.")


def parse_timezone(value: str) -> ZoneInfo:
    name = value.strip()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"TIMEZONE {name!r} is not a known time zone. Use a name like America/Los_Angeles."
        ) from None


def parse_allowed_chat_ids(value: str | None) -> frozenset[int] | None:
    if value is None or not value.strip():
        return None
    ids = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            raise ConfigError(
                f"ALLOWED_CHAT_IDS must be chat IDs separated by commas, like 123456789,-1001234567890. "
                f"{part!r} is not a number."
            ) from None
    return frozenset(ids) if ids else None


def _float(env: Mapping[str, str], name: str, default: float | None, low: float, high: float) -> float | None:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not low <= value <= high:  # also rejects nan
        raise ConfigError(f"{name} must be a number from {low:g} to {high:g}, not {raw!r}.")
    return value


def parse_irrigation(env: Mapping[str, str]) -> IrrigationConfig:
    d = IrrigationConfig()
    lat = _float(env, "FARM_LAT", None, -90, 90)
    lon = _float(env, "FARM_LON", None, -180, 180)
    if lon is not None and lat is None:
        raise ConfigError("FARM_LON is set but FARM_LAT is not. Set both, or neither.")
    config = IrrigationConfig(
        water_below_pct=_float(env, "WATER_BELOW_PCT", d.water_below_pct, 0, 100),
        kc=_float(env, "CITRUS_KC", d.kc, 0.1, 1.5),
        hold_off_below_mm=_float(env, "HOLD_OFF_BELOW_MM", d.hold_off_below_mm, 0, 500),
        weekly_from_mm=_float(env, "WEEKLY_FROM_MM", d.weekly_from_mm, 0, 500),
        twice_weekly_from_mm=_float(env, "TWICE_WEEKLY_FROM_MM", d.twice_weekly_from_mm, 0, 500),
        latitude=lat,
        longitude=lon,
    )
    if not config.hold_off_below_mm <= config.weekly_from_mm <= config.twice_weekly_from_mm:
        raise ConfigError("HOLD_OFF_BELOW_MM, WEEKLY_FROM_MM and TWICE_WEEKLY_FROM_MM must go up in that order.")
    return config


def load_config(env: Mapping[str, str] | None = None, *, require_token: bool = True) -> Config:
    env = os.environ if env is None else env
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if require_token:
        if not token:
            raise MissingTokenError()
        if not _TOKEN_RE.match(token):
            # Never echo the value: it may be a real token with a typo.
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN does not look like a bot token (digits, a colon, then about 35 "
                "letters). Copy it again from @BotFather into farm/bot/.env."
            )
    tz = parse_timezone(env.get("TIMEZONE") or DEFAULT_TIMEZONE)
    return Config(
        token=token,
        daily_at=parse_daily_at(env.get("DAILY_AT") or DEFAULT_DAILY_AT, tz),
        timezone=tz,
        allowed_chat_ids=parse_allowed_chat_ids(env.get("ALLOWED_CHAT_IDS")),
        scan_command=(env.get("SCAN_COMMAND") or "").strip() or None,
        irrigation=parse_irrigation(env),
    )


class RedactingFormatter(logging.Formatter):
    """Log formatter that replaces secrets anywhere in a record, tracebacks included."""

    def __init__(self, fmt: str, secrets: list[str]) -> None:
        super().__init__(fmt)
        self._secrets = sorted((s for s in secrets if s), key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "[redacted]")
        return _LOG_SECRET_RE.sub("[redacted]", text)


def setup_logging(secrets: list[str], level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # httpx logs every request URL at INFO, and Telegram URLs contain the token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
