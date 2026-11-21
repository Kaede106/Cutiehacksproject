"""Subscribed chats, kept in bot_state.json in the data folder (the bot's own file)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

STATE_FILE = "bot_state.json"

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._chats: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            chats = data["chats"]
            if not isinstance(chats, dict):
                raise TypeError("chats is not an object")
            return {str(int(k)): v if isinstance(v, dict) else {} for k, v in chats.items()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            backup = self.path.with_suffix(".json.bad")
            log.warning("Could not read %s (%s). Starting with no subscribers; old file kept as %s.",
                        self.path.name, exc, backup.name)
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            return {}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"chats": self._chats}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic, so a crash never leaves half a file

    def chats(self) -> list[int]:
        return sorted(int(k) for k in self._chats)

    def is_subscribed(self, chat_id: int) -> bool:
        return str(chat_id) in self._chats

    def subscribe(self, chat_id: int, now: datetime) -> bool:
        """Returns False if the chat was already subscribed."""
        if self.is_subscribed(chat_id):
            return False
        self._chats[str(chat_id)] = {"subscribed_at": now.isoformat(timespec="seconds")}
        self._save()
        return True

    def unsubscribe(self, chat_id: int) -> bool:
        """Returns False if the chat was not subscribed."""
        if self._chats.pop(str(chat_id), None) is None:
            return False
        self._save()
        return True
