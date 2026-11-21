import logging
from datetime import time
from zoneinfo import ZoneInfo

import pytest

from farm.bot.config import (MISSING_TOKEN, ConfigError, MissingTokenError, RedactingFormatter, load_config,
                             parse_allowed_chat_ids, parse_daily_at, parse_timezone)

TOKEN = "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ"
LA = ZoneInfo("America/Los_Angeles")


@pytest.mark.parametrize("value, expected", [
    ("09:00", time(9, 0)), ("9:00", time(9, 0)), (" 18:30 ", time(18, 30)), ("00:00", time(0, 0)),
    ("23:59", time(23, 59)),
])
def test_daily_at_valid(value, expected):
    parsed = parse_daily_at(value, LA)
    assert (parsed.hour, parsed.minute) == (expected.hour, expected.minute)
    assert parsed.tzinfo is LA


@pytest.mark.parametrize("value", ["24:00", "9:60", "9am", "9", "09:00:00", "", "nine", "-1:00", "9:5"])
def test_daily_at_invalid(value):
    with pytest.raises(ConfigError, match="DAILY_AT"):
        parse_daily_at(value, LA)


def test_timezone():
    assert parse_timezone(" Europe/Madrid ").key == "Europe/Madrid"
    with pytest.raises(ConfigError, match="TIMEZONE"):
        parse_timezone("Mars/Olympus")
    with pytest.raises(ConfigError, match="TIMEZONE"):
        parse_timezone("../../etc")


def test_allowed_chat_ids():
    assert parse_allowed_chat_ids(None) is None
    assert parse_allowed_chat_ids("  ") is None
    assert parse_allowed_chat_ids(",") is None
    assert parse_allowed_chat_ids("123, -1001234567890,") == frozenset({123, -1001234567890})
    with pytest.raises(ConfigError, match="ALLOWED_CHAT_IDS"):
        parse_allowed_chat_ids("123,@pablo")


def test_defaults():
    config = load_config({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert (config.daily_at.hour, config.daily_at.minute) == (9, 0)
    assert config.timezone.key == "America/Los_Angeles" and config.daily_at.tzinfo == config.timezone
    assert config.allowed_chat_ids is None
    assert config.scan_command is None


def test_full_config():
    config = load_config({"TELEGRAM_BOT_TOKEN": f" {TOKEN} ", "DAILY_AT": "07:15", "TIMEZONE": "UTC",
                          "ALLOWED_CHAT_IDS": "42", "SCAN_COMMAND": "python scan.py"})
    assert config.token == TOKEN
    assert (config.daily_at.hour, config.daily_at.minute, config.timezone.key) == (7, 15, "UTC")
    assert config.allowed_chat_ids == frozenset({42})
    assert config.scan_command == "python scan.py"
    assert TOKEN not in repr(config)


@pytest.mark.parametrize("env", [{}, {"TELEGRAM_BOT_TOKEN": ""}, {"TELEGRAM_BOT_TOKEN": "   "}])
def test_missing_token(env):
    with pytest.raises(MissingTokenError) as info:
        load_config(env)
    message = str(info.value)
    assert message == MISSING_TOKEN and "\n" not in message
    assert "@BotFather" in message and "/newbot" in message and "farm/bot/.env" in message


def test_malformed_token_is_not_echoed():
    bad = TOKEN[:-5]  # looks like a real token with a piece missing
    with pytest.raises(ConfigError) as info:
        load_config({"TELEGRAM_BOT_TOKEN": bad + "!"})
    assert bad not in str(info.value)
    assert "@BotFather" in str(info.value)


def test_preview_does_not_need_a_token():
    assert load_config({}, require_token=False).token == ""


def test_bad_setting_is_reported_even_with_a_token():
    with pytest.raises(ConfigError, match="DAILY_AT"):
        load_config({"TELEGRAM_BOT_TOKEN": TOKEN, "DAILY_AT": "9am"})


def test_log_formatter_redacts_the_token_everywhere():
    formatter = RedactingFormatter("%(message)s", [TOKEN, ""])
    try:
        raise RuntimeError(f"The token `{TOKEN}` was rejected by the server.")
    except RuntimeError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "url /bot%s/getMe", (TOKEN,), sys.exc_info())
    out = formatter.format(record)
    assert TOKEN not in out
    assert "[redacted]" in out
