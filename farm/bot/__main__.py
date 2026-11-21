"""python -m farm.bot [run]          start the Telegram bot
python -m farm.bot preview      print the message for the current data (no Telegram needed)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from .config import ConfigError, MissingTokenError, load_config, load_env_file, setup_logging
from .fixtures import FIXTURES

log = logging.getLogger("farm.bot")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m farm.bot", description="CutieFarm Telegram bot.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="start the bot (the default)")
    preview = sub.add_parser("preview", help="print the message for the current data, without Telegram")
    source = preview.add_mutually_exclusive_group()
    source.add_argument("--data", metavar="FOLDER", type=Path,
                        help="data folder to read (default: $CUTIEFARM_DATA or farm/data)")
    source.add_argument("--fixture", choices=sorted(FIXTURES), help="use built-in made-up data")
    preview.add_argument("--html", action="store_true", help="print the Telegram HTML instead of plain text")
    preview.add_argument("--water", action="store_true", help="print the /water reply instead of the daily message")
    seed_demo = sub.add_parser("seed-demo", help="write clearly marked demo data into the data folder ($CUTIEFARM_DATA)")
    seed_demo.add_argument("--week", action="store_true", help="include 7 days of scans and example harvest activity")
    return parser


def preview(args: argparse.Namespace) -> int:
    from farm.common import store

    from .access import photo_path
    from .app import build_message, water_advice
    from .compose import Message, compose, to_plain
    from .irrigation import advise, water_message

    config = load_config(require_token=False)
    now = datetime.now(config.timezone)
    if args.fixture:
        fx = FIXTURES[args.fixture](now)
        advice = advise(fx.history, fx.weather, now.date(), config.irrigation, now=now)
        if args.water:
            message = Message(water_message(advice, now.date()))
        else:
            message = compose(fx.scan, fx.sensors, now, scan_command=config.scan_command, irrigation=advice)
        header = f"Fixture {args.fixture!r} (made-up data, not from the grove)"
        data = None
    else:
        if args.data:
            if not args.data.is_dir():
                print(f"No such folder: {args.data}", file=sys.stderr)
                return 2
            os.environ["CUTIEFARM_DATA"] = str(args.data.resolve())
        data = store.data_dir()
        if args.water:
            message = Message(water_message(water_advice(config, now), now.date()))
        else:
            message = build_message(config, now)
        header = f"Data folder {data}"

    out = message.text if args.html else to_plain(message.text)
    print(f"--- {header}, {now:%Y-%m-%d %H:%M %Z} ---")
    print(out)
    for photo in message.photos:
        where = "(fixture, no real file)" if data is None else str(photo_path(data, photo.path))
        caption = photo.caption if args.html else to_plain(photo.caption)
        print(f"[photo] {photo.path}  {where}\n        {caption}")
    return 0


def run() -> int:
    from telegram.error import InvalidToken, NetworkError

    from .app import build_application, clock

    config = load_config()
    setup_logging([config.token])
    if config.allowed_chat_ids is None:
        log.warning("ALLOWED_CHAT_IDS is not set: anyone who finds this bot can use it. "
                    "Send /start to learn your chat ID, then set ALLOWED_CHAT_IDS in farm/bot/.env.")
    else:
        log.info("Answering %d allowed chat(s) only.", len(config.allowed_chat_ids))

    from farm.common import store

    app = build_application(config)
    log.info("Data folder: %s", store.data_dir())
    log.info("Daily message at %s %s. Press Ctrl+C to stop.", clock(config.daily_at), config.timezone.key)
    try:
        app.run_polling(drop_pending_updates=False)
    except InvalidToken:
        # PTB's own message for this error contains the token, so do not print it.
        print("Telegram rejected TELEGRAM_BOT_TOKEN. Copy it again from @BotFather into farm/bot/.env.",
              file=sys.stderr)
        return 2
    except NetworkError as exc:
        print(f"Could not reach Telegram ({type(exc).__name__}). Check the internet connection.",
              file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    load_env_file()
    try:
        if args.command == "seed-demo":
            from farm.bot.demo import seed
            print(f"Demo data written to {seed(week=args.week)}")
            return 0
        return preview(args) if args.command == "preview" else run()
    except MissingTokenError as exc:
        print(exc, file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
