"""Who may use the bot, and which files it may send."""
from __future__ import annotations

from pathlib import Path

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def is_allowed(chat_id: int | None, allowed: frozenset[int] | None) -> bool:
    """With no allowlist anyone may use the bot; with one, only the listed chats."""
    if chat_id is None:
        return False
    return allowed is None or chat_id in allowed


def photo_path(data_dir: Path, relative: str) -> Path | None:
    """Resolve a photo path from a scan record, or None if it must not be sent.

    Paths in scans.jsonl are data, so a bad record must not make the bot upload
    an arbitrary file from the laptop: the file has to be an image inside the
    data folder.
    """
    if not isinstance(relative, str) or not relative:
        return None
    base = data_dir.resolve()
    try:
        path = (base / relative).resolve()
    except (OSError, ValueError):
        return None
    if not path.is_relative_to(base) or path.suffix.lower() not in PHOTO_SUFFIXES:
        return None
    return path if path.is_file() else None
