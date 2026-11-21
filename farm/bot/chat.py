"""Free-text conversation for the CutieFarm bot.

Two layers:
- A keyword matcher (English and Spanish) that always works: it maps "status", "water",
  "mold"... to the same answers as the commands.
- When OPENAI_API_KEY is set, an OpenAI model answers anything else in the grower's own
  language, using ONLY the latest scan, sensor readings and watering advice as context.

The model call is capped per chat and per day (CHAT_DAILY_LIMIT, CHAT_GLOBAL_DAILY_LIMIT),
because anyone who scans the landing page's QR code can talk to the bot.
What leaves the laptop: the question, the last few turns of that chat and the farm summary
below. No photos are sent to OpenAI.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections import defaultdict, deque
from datetime import date, datetime
from typing import Any, Mapping

import httpx

from .voice import Transcriber

log = logging.getLogger("farm.bot.chat")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-6-luna"
HISTORY_TURNS = 6

LABEL_TEXT = {"unripe": "unripe", "ripening": "ripening", "ripe": "ready to pick", "mold": "possible mold"}

SYSTEM_PROMPT = """You are CutieFarm, a small assistant that looks after an orange grove.
A camera labels each orange (unripe, ripening, ready to pick, possible mold) and sensors read the soil, temperature, humidity and wind.
Answer the grower's question using ONLY the farm data below. Rules:
- Reply in the same language the grower writes in. Be short: one to four sentences, plain text, no Markdown.
- Never invent oranges, numbers, dates, positions or readings that are not in the data. If the data can't answer, say so plainly and suggest /status or /water.
- Positions (left, centre, right, top, bottom) refer to where each orange appears in the camera picture.
- If the data is marked as demo or simulated, mention that once when it matters.
- Watering advice is a rule of thumb, not agronomic certainty.
- For anything unrelated to the grove, say briefly that you only know about this grove.

FARM DATA
{context}"""


# ---------------------------------------------------------------- keyword intents

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_INTENTS = [
    ("water", r"\b(water|watering|irrigat\w*|regar|riego|riega\w*|agua)\b"),
    ("status", r"\b(status|estado|today|hoy|naranj\w*|orange\w*|pick\w*|recog\w*|cosech\w*|harvest\w*|"
               r"madur\w*|ripe\w*|ready|listas?|mold\w*|moho|hongos?|fung\w*|resumen|summary)\b"),
    ("help", r"\b(help|ayuda|hola|hello|hi|hey|buenas|que (puedes|sabes) hacer|what can you do)\b"),
]


def keyword_intent(text: str) -> str | None:
    """'water', 'status', 'help' or None. Watering wins over status when both appear."""
    t = _norm(text)
    for name, pattern in _INTENTS:
        if re.search(pattern, t):
            return name
    return None


# ---------------------------------------------------------------- farm context

def _positions(fruits: list[Mapping[str, Any]]) -> dict[int, str]:
    """Rough place of each orange in the picture, from its bounding box."""
    boxes = {f["id"]: f.get("bbox") for f in fruits if isinstance(f.get("bbox"), (list, tuple)) and len(f["bbox"]) == 4}
    if not boxes:
        return {}
    xs = [b[0] + b[2] / 2 for b in boxes.values()]
    ys = [b[1] + b[3] / 2 for b in boxes.values()]
    x0, x1 = min(b[0] for b in boxes.values()), max(b[0] + b[2] for b in boxes.values())
    y0, y1 = min(b[1] for b in boxes.values()), max(b[1] + b[3] for b in boxes.values())

    def third(v: float, lo: float, hi: float, names: tuple[str, str, str]) -> str:
        if hi - lo < 1:
            return names[1]
        r = (v - lo) / (hi - lo)
        return names[0] if r < 1 / 3 else names[2] if r > 2 / 3 else names[1]

    out = {}
    for (fid, _), cx, cy in zip(boxes.items(), xs, ys):
        out[fid] = f"{third(cy, y0, y1, ('top', 'middle', 'bottom'))} {third(cx, x0, x1, ('left', 'centre', 'right'))}"
    return out


def farm_context(scan: Mapping[str, Any] | None, sensors: Mapping[str, Any] | None,
                 watering: str | None, now: datetime) -> str:
    """A compact, factual summary of what the bot knows right now."""
    lines = [f"Now: {now:%A %d %B %Y, %H:%M} (grower's local time)."]
    if not scan:
        lines.append("Camera: no scan recorded yet.")
    else:
        taken = scan.get("taken_at", "unknown time")
        flags = []
        if scan.get("demo"):
            flags.append("DEMO DATA: the camera isn't connected yet, this scan is an example")
        if "heuristic" in str(scan.get("model", "")).lower():
            flags.append("labels come from a colour check, not the trained model yet")
        lines.append(f"Latest scan: {taken}." + (f" ({'; '.join(flags)})" if flags else ""))
        summary = scan.get("summary") or {}
        lines.append("Counts: " + ", ".join(f"{summary.get(k, 0)} {LABEL_TEXT[k]}" for k in LABEL_TEXT) + ".")
        fruits = scan.get("fruits") or []
        pos = _positions(fruits)
        for f in fruits:
            where = f", {pos[f['id']]} of the picture" if f.get("id") in pos else ""
            lines.append(f"- Orange {f.get('id')}: {LABEL_TEXT.get(f.get('label'), f.get('label'))}"
                         f" ({f.get('confidence', 'unknown')} confidence){where}.")
    if sensors:
        sim = " (SIMULATED, not real readings)" if sensors.get("simulated") else ""
        parts = []
        for key, label, unit in (("soil_moisture_pct", "soil moisture", "%"), ("temperature_c", "temperature", " °C"),
                                 ("humidity_pct", "humidity", "%"), ("wind_ms", "wind", " m/s")):
            if sensors.get(key) is not None:
                parts.append(f"{label} {sensors[key]}{unit}")
        lines.append(f"Sensors at {sensors.get('taken_at', 'unknown time')}{sim}: " + (", ".join(parts) or "no values") + ".")
    else:
        lines.append("Sensors: none connected yet.")
    if watering:
        lines.append("Watering advice: " + watering)
    return "\n".join(lines)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


# ---------------------------------------------------------------- limits and history

class Limits:
    def __init__(self, per_chat: int, total: int) -> None:
        self.per_chat, self.total = per_chat, total
        self._day: date | None = None
        self._counts: dict[int, int] = defaultdict(int)
        self._total = 0

    def take(self, chat_id: int, today: date) -> bool:
        if today != self._day:
            self._day, self._counts, self._total = today, defaultdict(int), 0
        if self._counts[chat_id] >= self.per_chat or self._total >= self.total:
            return False
        self._counts[chat_id] += 1
        self._total += 1
        return True


class Conversation:
    """Talks to OpenAI. Disabled (enabled is False) when OPENAI_API_KEY is not set."""

    def __init__(self, env: Mapping[str, str] | None = None, client: httpx.AsyncClient | None = None) -> None:
        env = os.environ if env is None else env
        self.api_key = (env.get("OPENAI_API_KEY") or "").strip()
        self.model = (env.get("OPENAI_MODEL") or DEFAULT_MODEL).strip()
        self.transcriber = Transcriber(self.api_key, env.get("OPENAI_TRANSCRIBE_MODEL"), client)
        self.limits = Limits(int(env.get("CHAT_DAILY_LIMIT") or 30), int(env.get("CHAT_GLOBAL_DAILY_LIMIT") or 500))
        self.history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def reply(self, chat_id: int, question: str, context: str, today: date) -> str | None:
        """The model's answer, or None if it is disabled, over the limit or failed
        (the caller then falls back to keywords)."""
        if not self.enabled:
            return None
        if not self.limits.take(chat_id, today):
            return "That's all the questions I can answer today. /status and /water still work."
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
        messages += list(self.history[chat_id])
        messages.append({"role": "user", "content": question[:1000]})
        body = {"model": self.model, "messages": messages, "max_completion_tokens": 400}
        try:
            client = self._client or httpx.AsyncClient(timeout=30)
            try:
                r = await client.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
            finally:
                if self._client is None:
                    await client.aclose()
            if r.status_code != 200:
                log.warning("OpenAI returned HTTP %s for chat %s.", r.status_code, chat_id)
                return None
            answer = (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:  # network, timeout, bad JSON: never crash the bot
            log.warning("OpenAI call failed for chat %s (%s).", chat_id, type(exc).__name__)
            return None
        if not answer:
            return None
        self.history[chat_id].append({"role": "user", "content": question[:1000]})
        self.history[chat_id].append({"role": "assistant", "content": answer})
        return answer

    async def reword(self, chat_id: int, reply: str, caption: str, today: date) -> str | None:
        """Say a fixed reply in the language this chat uses, keeping every fact. None means:
        send the reply as it is (no model, no earlier messages to take the language from, or a failure)."""
        if not self.enabled or not (self.history[chat_id] or caption.strip()):
            return None
        if not self.limits.take(chat_id, today):
            return None
        system = ("Rewrite the assistant reply below for the grower, in the language they have been "
                  "writing in. Keep every fact, label and confidence exactly; add nothing. Plain text, "
                  "at most three sentences.\n\nREPLY\n" + reply)
        messages = [{"role": "system", "content": system}, *list(self.history[chat_id])]
        messages.append({"role": "user", "content": caption.strip() or "(sent a photo of an orange)"})
        body = {"model": self.model, "messages": messages, "max_completion_tokens": 300}
        try:
            client = self._client or httpx.AsyncClient(timeout=30)
            try:
                r = await client.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
            finally:
                if self._client is None:
                    await client.aclose()
            if r.status_code != 200:
                return None
            text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:
            log.warning("OpenAI reword failed for chat %s (%s).", chat_id, type(exc).__name__)
            return None
        if text:
            self.history[chat_id].append({"role": "assistant", "content": text})
        return text or None
