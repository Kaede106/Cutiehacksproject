import json
from datetime import datetime, timezone

from farm.bot.state import State

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)


def test_subscribe_and_unsubscribe_persist(tmp_path):
    path = tmp_path / "bot_state.json"
    state = State(path)
    assert state.chats() == []
    assert state.subscribe(42, NOW) is True
    assert state.subscribe(42, NOW) is False
    assert state.subscribe(-100, NOW) is True
    assert State(path).chats() == [-100, 42]
    assert State(path).unsubscribe(42) is True
    assert State(path).chats() == [-100]
    assert State(path).unsubscribe(42) is False
    assert json.loads(path.read_text())["chats"]["-100"]["subscribed_at"] == "2026-11-21T09:00:00+00:00"


def test_corrupt_state_is_kept_aside_and_bot_starts_empty(tmp_path):
    path = tmp_path / "bot_state.json"
    path.write_text("{not json")
    state = State(path)
    assert state.chats() == []
    assert (tmp_path / "bot_state.json.bad").read_text() == "{not json"
    state.subscribe(7, NOW)
    assert State(path).chats() == [7]
