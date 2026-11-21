"""The bot's append-only harvest log and seven-day recap."""
from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Iterable, Iterator

from farm.common import store

from .compose import _counts, _esc, _parse_time

HARVEST_FILE = "harvest.jsonl"
KINDS = ("picked", "removed", "watered")
_lock = Lock()

# Match the entire sentence. A permissive tail would accept questions,
# alternatives, quoted reports and qualifications such as "in my dream".
_NUMBER = r"(?P<count>[1-9][0-9]*)"
_PATTERNS = (
    ("picked", rf"(?:i )?picked {_NUMBER}(?: oranges?)?(?: today)?"),
    ("picked", rf"(?:(?:yo )?recog[ií]|(?:yo )?he recogido) {_NUMBER}(?: naranjas?)?(?: hoy)?"),
    ("removed", rf"(?:i )?removed (?:{_NUMBER}(?: (?:moldy )?oranges?)?|the moldy one)(?: today)?"),
    ("removed", rf"(?:(?:yo )?quit[eé]|(?:yo )?he quitado) {_NUMBER}(?: naranjas?)?(?: con (?:hongo|moho))?(?: hoy)?"),
    ("watered", r"(?:i )?watered(?: the (?:trees|orange trees|plants|grove))?(?: today)?"),
    ("watered", r"(?:(?:yo )?regu[eé]|(?:yo )?he regado)(?: (?:los (?:árboles|naranjos)|las plantas))?(?: hoy)?"),
)


def parse_text(text: str) -> tuple[str, int] | None:
    sentence = " ".join(unicodedata.normalize("NFC", text).casefold().split())
    for kind, pattern in _PATTERNS:
        if match := re.fullmatch(pattern + r"[.!]?", sentence):
            return kind, int(match.groupdict().get("count") or 1)
    return None


def parse_command(text: str) -> tuple[str, int] | None:
    command = re.fullmatch(r"/(picked|removed|watered)(?:@[a-z0-9_]+)?(?:\s+(.*))?",
                           text.strip(), re.IGNORECASE)
    if command is None:
        return None
    kind, count = command[1].lower(), command[2]
    if kind == "watered":
        return (kind, 1) if count is None else None
    if count and (match := re.fullmatch(_NUMBER, count)):
        return kind, int(match["count"])
    return None


def append_entry(
    chat_id: int | None, kind: str, count: int, text: str, *,
    taken_at: str | None = None, demo: bool = False,
) -> None:
    with _lock:
        record = dict(taken_at=taken_at or store.now_iso(), chat_id=chat_id, kind=kind, count=count, text=text)
        if demo:
            record["demo"] = True
        store._append(HARVEST_FILE, record)


def entries(chat_id: int, *, include_demo: bool = False) -> list[dict[str, Any]]:
    """Replay this chat's entries in file order, applying each undo marker once."""
    active = []
    examples = []
    for record in store._read(HARVEST_FILE):
        if not isinstance(record, dict):
            continue
        kind, count = record.get("kind"), record.get("count")
        if kind in KINDS and type(count) is int and count > 0:
            if record.get("demo"):
                if include_demo and record.get("chat_id") in (None, chat_id):
                    examples.append(record)
            elif record.get("chat_id") == chat_id:
                active.append(record)
        elif record.get("undo") is True and record.get("chat_id") == chat_id and active:
            active.pop()
    return active + examples


def undo(chat_id: int) -> bool:
    with _lock:
        if not entries(chat_id):
            return False
        store._append(HARVEST_FILE, dict(taken_at=store.now_iso(), chat_id=chat_id, undo=True))
        return True


async def maybe_record(chat_id: int, message: Any, *, command: bool = False) -> bool:
    text = message.text or ""
    parse = parse_command if command else parse_text
    action = parse(text)
    if action is None:
        return False
    kind, count = action
    await asyncio.to_thread(append_entry, chat_id, kind, count, text)
    await message.reply_text("Logged: watered today." if kind == "watered" else f"Logged: {count} {kind} today.")
    return True


def _recent(
    records: Iterable[Any], now: datetime,
) -> Iterator[tuple[datetime, dict[str, Any]]]:
    end = now.astimezone(timezone.utc)
    start = end - timedelta(days=7)
    for record in records:
        if isinstance(record, dict) and (taken := _parse_time(record.get("taken_at"), now)) is not None:
            taken = taken.astimezone(timezone.utc)
            if start <= taken <= end:
                yield taken, record


def _example_note(records: Iterable[dict[str, Any]]) -> str:
    flags = {flag for record in records for flag in ("demo", "simulated") if record.get(flag)}
    return f" <i>Includes {' and '.join(sorted(flags))} data.</i>" if flags else ""


def week_summary(chat_id: int, now: datetime) -> str:
    scans = sorted(_recent(store._read(store.SCANS_FILE), now), key=lambda item: item[0])
    actions = list(_recent(entries(chat_id, include_demo=True), now))

    scan_note = _example_note(record for _, record in scans)
    if len(scans) < 2:
        scan_line = "Not enough scan data. At least two scans are needed."
    else:
        first, latest = _counts(scans[0][1]), _counts(scans[-1][1])
        labels = (("ripe", "Ready"), ("ripening", "Ripening"), ("unripe", "Unripe"), ("mold", "Possible mold"))
        scan_line = " · ".join(f"{label} {first[key]} → {latest[key]}" for key, label in labels)

    harvest_note = _example_note(record for _, record in actions)
    if not actions:
        harvest_line = "No harvest activity logged in the last 7 days."
    else:
        totals = dict.fromkeys(KINDS, 0)
        watered_days = set()
        for taken, record in actions:
            kind = record["kind"]
            totals[kind] += record["count"]
            if kind == "watered":
                watered_days.add(taken.astimezone(now.tzinfo).date())
        days = ", ".join(f"{day:%a} {day:%b} {day.day}" for day in sorted(watered_days))
        harvest_line = f"Picked {totals['picked']} · Removed {totals['removed']}\nWatered: {days or 'no days logged'}"

    return (
        f"<b>Last 7 days</b>\n\n<b>Scans</b>{scan_note}\n{_esc(scan_line)}"
        f"\n\n<b>Harvest log</b>{harvest_note}\n{_esc(harvest_line)}"
    )
