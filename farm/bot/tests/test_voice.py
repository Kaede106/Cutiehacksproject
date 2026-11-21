"""Voice and audio handling with fake Telegram updates and mocked OpenAI calls."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from telegram import Audio, Chat, Message, Update, Voice
from telegram.error import TelegramError

from farm.bot.app import Handlers, build_application
from farm.bot.chat import OPENAI_URL, Conversation
from farm.bot.config import load_config
from farm.bot.state import State
from farm.bot.voice import MAX_AUDIO_BYTES, TRANSCRIPTION_URL


@pytest.fixture
def make_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    requests = []

    def make(respond=None, *, env=None, allowed=None):
        def handle(request):
            requests.append(request)
            assert respond is not None, "Unexpected request to OpenAI"
            return respond(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        conv = Conversation({"OPENAI_API_KEY": "sk-test"} if env is None else env, client)
        config = load_config({"ALLOWED_CHAT_IDS": allowed or ""}, require_token=False)
        return Handlers(config, State(tmp_path / "bot_state.json"), conv), requests

    return make


def fake_update(chat_id=1, *, duration=60, audio=False, file_size=None):
    file = SimpleNamespace(file_path="https://example.test/files/audio.bin",
                           download_as_bytearray=AsyncMock(return_value=bytearray(b"audio-bytes")))
    media = SimpleNamespace(duration=duration, file_size=file_size, get_file=AsyncMock(return_value=file))
    if audio:
        media.file_name = "grower question.M4A"
        media.mime_type = "audio/mp4"
    message = SimpleNamespace(voice=None if audio else media, audio=media if audio else None,
                              reply_text=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id, type="private"), effective_message=message), media


def test_application_registers_voice_and_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    config = load_config({"TELEGRAM_BOT_TOKEN": "12345:" + "x" * 35})
    app = build_application(config)
    assert app.update_processor.max_concurrent_updates == 8
    for field, media in (("voice", Voice("file", "unique", 1)), ("audio", Audio("file", "unique", 1))):
        message = Message(1, datetime.now(config.timezone), Chat(1, "private"), **{field: media})
        update = Update(1, message=message)
        handler = next(handler for handler in app.handlers[0] if handler.check_update(update))
        assert handler.callback.__func__ is Handlers.voice


def test_voice_transcribes_and_falls_back_to_keywords(make_handlers):
    def respond(request):
        if str(request.url) == TRANSCRIPTION_URL:
            return httpx.Response(200, json={"text": "  Any oranges ready?  "})
        return httpx.Response(503)

    handlers, requests = make_handlers(respond)
    update, media = fake_update()
    message = update.effective_message
    context = SimpleNamespace(bot=AsyncMock())
    sent = []
    message.reply_text.side_effect = sent.append
    context.bot.send_message.side_effect = lambda _, text, **kw: sent.append(text)
    asyncio.run(handlers.voice(update, context))

    assert [str(r.url) for r in requests] == [TRANSCRIPTION_URL, OPENAI_URL]
    upload = requests[0]
    assert upload.method == "POST"
    assert upload.headers["Authorization"] == "Bearer sk-test"
    assert upload.headers["Content-Type"].startswith("multipart/form-data;")
    assert b'name="model"\r\n\r\ngpt-4o-mini-transcribe' in upload.content
    assert b'name="file"; filename="audio.ogg"\r\nContent-Type: audio/ogg' in upload.content
    assert b"audio-bytes" in upload.content
    media.get_file.return_value.download_as_bytearray.assert_awaited_once()
    assert sent[0] == 'You said: "Any oranges ready?"'
    assert "No scan in the last 24 hours." in sent[1]


def test_audio_transcribes_and_answers_with_model(make_handlers):
    question = "¿Y las de la izquierda?"
    answer = "Todavía están verdes."

    def respond(request):
        if str(request.url) == TRANSCRIPTION_URL:
            return httpx.Response(200, json={"text": question})
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    env = {"OPENAI_API_KEY": "sk-test", "OPENAI_TRANSCRIBE_MODEL": "gpt-transcribe"}
    handlers, requests = make_handlers(respond, env=env)
    update, _ = fake_update(audio=True, duration=timedelta(seconds=60))
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))

    assert [str(r.url) for r in requests] == [TRANSCRIPTION_URL, OPENAI_URL]
    assert b'name="model"\r\n\r\ngpt-transcribe' in requests[0].content
    assert b'filename="audio.m4a"\r\nContent-Type: audio/mp4' in requests[0].content
    assert b"grower question" not in requests[0].content
    assert json.loads(requests[1].content)["messages"][-1] == {"role": "user", "content": question}
    assert [call.args[0] for call in update.effective_message.reply_text.await_args_list] == [
        f'You said: "{question}"', answer,
    ]


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("duration", [61, None, 0, -1, timedelta(0)])
def test_invalid_audio_duration_is_rejected(make_handlers, audio, duration):
    handlers, requests = make_handlers()
    update, media = fake_update(duration=duration, audio=audio)
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    assert "60 seconds or less" in update.effective_message.reply_text.await_args.args[0]
    media.get_file.assert_not_called()
    assert requests == []


def test_audio_over_size_limit_is_rejected_before_download(make_handlers):
    handlers, requests = make_handlers()
    update, media = fake_update(file_size=MAX_AUDIO_BYTES + 1)
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    media.get_file.assert_not_called()
    assert "2,000,000 bytes" in update.effective_message.reply_text.await_args.args[0]
    assert requests == []
    assert handlers.conversation.limits._total == 0


def test_audio_download_over_size_limit_never_reaches_openai(make_handlers):
    handlers, requests = make_handlers()
    update, media = fake_update(file_size=MAX_AUDIO_BYTES)
    download = media.get_file.return_value.download_as_bytearray
    download.return_value = bytearray(MAX_AUDIO_BYTES + 1)
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    download.assert_awaited_once()
    assert "couldn't transcribe" in update.effective_message.reply_text.await_args.args[0]
    assert requests == []


def test_no_key_suggests_commands(make_handlers):
    handlers, requests = make_handlers(env={})
    update, media = fake_update()
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    reply = update.effective_message.reply_text.await_args.args[0]
    assert "OPENAI_API_KEY" in reply and "/status" in reply and "/water" in reply
    media.get_file.assert_not_called()
    assert requests == []


@pytest.mark.parametrize("status, payload", [(500, {"error": "private"}), (200, {"text": "  "})])
def test_transcription_error_or_empty_text_prompts_retry(make_handlers, caplog, status, payload):
    handlers, requests = make_handlers(lambda r: httpx.Response(status, json=payload))
    update, _ = fake_update()
    context = SimpleNamespace(bot=AsyncMock())
    asyncio.run(handlers.voice(update, context))
    update.effective_message.reply_text.assert_awaited_once()
    assert "couldn't transcribe" in update.effective_message.reply_text.await_args.args[0]
    context.bot.send_message.assert_not_called()
    assert [str(r.url) for r in requests] == [TRANSCRIPTION_URL]
    assert "private" not in caplog.text and "sk-test" not in caplog.text


def test_telegram_download_error_prompts_retry(make_handlers):
    handlers, requests = make_handlers()
    update, media = fake_update()
    media.get_file.side_effect = TelegramError("File is too big")
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    assert "couldn't transcribe" in update.effective_message.reply_text.await_args.args[0]
    assert requests == []


@pytest.mark.parametrize("limit, next_chat", [("CHAT_DAILY_LIMIT", 1), ("CHAT_GLOBAL_DAILY_LIMIT", 2)])
def test_transcription_attempts_use_shared_limits(make_handlers, limit, next_chat):
    env = {"OPENAI_API_KEY": "sk-test", limit: "1"}
    handlers, requests = make_handlers(lambda r: httpx.Response(500), env=env)
    first, _ = fake_update()
    second, media = fake_update(next_chat)
    context = SimpleNamespace(bot=AsyncMock())
    asyncio.run(handlers.voice(first, context))
    asyncio.run(handlers.voice(second, context))
    assert "today's audio limit" in second.effective_message.reply_text.await_args.args[0]
    media.get_file.assert_not_called()
    typed = SimpleNamespace(effective_chat=second.effective_chat,
                            effective_message=SimpleNamespace(text="what now?", reply_text=AsyncMock()))
    asyncio.run(handlers.text(typed, context))
    assert "questions I can answer today" in typed.effective_message.reply_text.await_args.args[0]
    assert [str(r.url) for r in requests] == [TRANSCRIPTION_URL]


def test_voice_respects_allowlist(make_handlers):
    handlers, requests = make_handlers(allowed="111")
    update, media = fake_update(222)
    context = SimpleNamespace(bot=AsyncMock())
    asyncio.run(handlers.voice(update, context))
    media.get_file.assert_not_called()
    update.effective_message.reply_text.assert_not_called()
    context.bot.send_message.assert_not_called()
    assert requests == []


def test_voice_can_log_a_harvest(make_handlers, tmp_path):
    def respond(request):
        assert str(request.url) == TRANSCRIPTION_URL, "a harvest log must not reach the chat model"
        return httpx.Response(200, json={"text": "He recogido 3 naranjas"})

    handlers, requests = make_handlers(respond)
    update, _ = fake_update()
    message = update.effective_message
    asyncio.run(handlers.voice(update, SimpleNamespace(bot=AsyncMock())))
    replies = [c.args[0] for c in message.reply_text.call_args_list]
    assert replies == ['You said: "He recogido 3 naranjas"', "Logged: 3 picked today."]
    assert '"kind":"picked"' in (tmp_path / "harvest.jsonl").read_text(encoding="utf-8").replace(" ", "")
