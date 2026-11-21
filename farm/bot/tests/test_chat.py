import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest

from farm.bot.chat import Conversation, Limits, _positions, farm_context, keyword_intent

NOW = datetime(2026, 11, 21, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("text,intent", [
    ("¿Riego mañana?", "water"),
    ("when should I water", "water"),
    ("¿Cuántas naranjas están listas?", "status"),
    ("any mold today?", "status"),
    ("hay hongos?", "status"),
    ("hola", "help"),
    ("Y las de la izquierda?", None),
    ("tell me a joke", None),
])
def test_keyword_intent(text, intent):
    assert keyword_intent(text) == intent


def test_positions_split_the_picture_in_thirds():
    fruits = [{"id": 1, "bbox": [0, 0, 10, 10]}, {"id": 2, "bbox": [100, 100, 10, 10]},
              {"id": 3, "bbox": [50, 50, 10, 10]}]
    assert _positions(fruits) == {1: "top left", 2: "bottom right", 3: "middle centre"}


def test_context_marks_demo_and_simulated_data():
    scan = {"taken_at": "2026-11-21T10:00:00-08:00", "demo": True, "model": "color-heuristic-v1",
            "summary": {"ripe": 1, "mold": 1},
            "fruits": [{"id": 1, "label": "ripe", "confidence": "high", "bbox": [0, 0, 10, 10]},
                       {"id": 2, "label": "mold", "confidence": "medium", "bbox": [90, 0, 10, 10]}]}
    sensors = {"taken_at": "x", "simulated": True, "soil_moisture_pct": 40, "wind_ms": None}
    text = farm_context(scan, sensors, "Water on Thursday.", NOW)
    assert "DEMO DATA" in text and "SIMULATED" in text
    assert "Orange 2: possible mold (medium confidence), middle right of the picture." in text
    assert "wind" not in text  # null sensors are left out
    assert "Water on Thursday." in text


def test_context_without_data_says_so():
    text = farm_context(None, None, None, NOW)
    assert "no scan recorded yet" in text and "none connected yet" in text


def test_limits_per_chat_and_total_reset_daily():
    limits = Limits(per_chat=2, total=3)
    d = date(2026, 11, 21)
    assert limits.take(1, d) and limits.take(1, d)
    assert not limits.take(1, d)           # chat 1 used its 2
    assert limits.take(2, d)               # total is now 3
    assert not limits.take(3, d)           # global cap reached
    assert limits.take(1, date(2026, 11, 22))  # new day


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_conversation_disabled_without_key():
    conv = Conversation(env={})
    assert not conv.enabled
    assert run(conv.reply(1, "hola", "ctx", NOW.date())) is None


def test_conversation_sends_context_and_keeps_history():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"choices": [{"message": {"content": "Las de la izquierda están verdes."}}]})

    conv = Conversation(env={"OPENAI_API_KEY": "sk-test"}, client=_client(handler))
    assert run(conv.reply(7, "¿Y las de la izquierda?", "FACTS-123", NOW.date())) == "Las de la izquierda están verdes."
    run(conv.reply(7, "¿y la del hongo?", "FACTS-123", NOW.date()))
    body = seen[-1]
    assert body["model"] == "gpt-6-luna"
    assert "FACTS-123" in body["messages"][0]["content"]
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]


def test_conversation_failure_returns_none():
    conv = Conversation(env={"OPENAI_API_KEY": "sk-test"}, client=_client(lambda r: httpx.Response(500)))
    assert run(conv.reply(1, "hola", "ctx", NOW.date())) is None


def test_conversation_over_limit_says_so():
    conv = Conversation(env={"OPENAI_API_KEY": "sk-test", "CHAT_DAILY_LIMIT": "0"},
                        client=_client(lambda r: httpx.Response(500)))
    assert "questions I can answer today" in run(conv.reply(1, "hola", "ctx", NOW.date()))
