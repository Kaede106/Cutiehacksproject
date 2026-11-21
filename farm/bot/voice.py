"""Download Telegram audio in memory and send it to OpenAI for transcription."""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import httpx
from telegram import Audio, Voice
from telegram.error import TelegramError

log = logging.getLogger("farm.bot.voice")

TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_MODEL = "gpt-4o-mini-transcribe"
MAX_DURATION = 60
MAX_AUDIO_BYTES = 2_000_000
_AUDIO_TYPES = {
    ".flac": "audio/flac", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4", ".mpeg": "audio/mpeg", ".mpga": "audio/mpeg",
    ".ogg": "audio/ogg", ".wav": "audio/wav", ".webm": "audio/webm",
}
_MIME_EXTENSIONS = {mime: ext for ext, mime in _AUDIO_TYPES.items()}
_MIME_EXTENSIONS.update({"audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a"})


def too_long(media: Audio | Voice) -> bool:
    duration = media.duration
    seconds = duration.total_seconds() if isinstance(duration, timedelta) else duration
    return seconds is None or not 0 < seconds <= MAX_DURATION


def too_large(media: Audio | Voice) -> bool:
    return media.file_size is not None and media.file_size > MAX_AUDIO_BYTES


def _audio_extension(media: Audio, file_path: str | None) -> str | None:
    for name in (media.file_name, urlsplit(file_path or "").path):
        ext = PurePosixPath(name or "").suffix.lower()
        if ext in _AUDIO_TYPES:
            return ext
    mime = (media.mime_type or "").partition(";")[0].strip().lower()
    return _MIME_EXTENSIONS.get(mime)


class Transcriber:
    def __init__(self, api_key: str, model: str | None, client: httpx.AsyncClient | None) -> None:
        self._api_key = api_key
        self.model = (model or "").strip() or DEFAULT_MODEL
        self._client = client

    async def transcribe(self, media: Audio | Voice, *, is_voice: bool) -> str | None:
        if too_large(media):
            return None
        try:
            file = await media.get_file()
            ext = ".ogg" if is_voice else _audio_extension(media, file.file_path)
            if ext is None:
                return None
            content = bytes(await file.download_as_bytearray())
            if len(content) > MAX_AUDIO_BYTES:
                return None
            client = self._client or httpx.AsyncClient(timeout=30)
            try:
                response = await client.post(
                    TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data={"model": self.model, "response_format": "json"},
                    files={"file": (f"audio{ext}", content, _AUDIO_TYPES[ext])},
                )
            finally:
                if self._client is None:
                    await client.aclose()
            response.raise_for_status()
            payload = response.json()
        except (TelegramError, OSError, RuntimeError, httpx.HTTPError, ValueError) as exc:
            log.warning("Audio transcription failed (%s).", type(exc).__name__)
            return None
        text = payload.get("text") if isinstance(payload, dict) else None
        return text.strip() if isinstance(text, str) else None
