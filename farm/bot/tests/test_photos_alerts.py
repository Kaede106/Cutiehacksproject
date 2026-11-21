import asyncio
import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image, ImageDraw

from farm.bot.app import mold_alert
from farm.bot.photo import classify_photo, photo_reply
from farm.common import store

from test_handlers import context, data, handlers, update  # noqa: F401  (fixtures and helpers)


def run(coro):
    return asyncio.run(coro)


def jpeg(fill, bg=(40, 90, 50), spots=()):
    im = Image.new("RGB", (600, 450), bg)
    d = ImageDraw.Draw(im)
    d.ellipse([120, 45, 480, 405], fill=fill)
    for x, y, r in spots:
        d.ellipse([x - r - 12, y - r - 12, x + r + 12, y + r + 12], fill=(238, 238, 230))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(90, 160, 150))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return b.getvalue()


def test_classify_photo_labels():
    assert classify_photo(jpeg((240, 130, 20))).label == "ripe"
    assert classify_photo(jpeg((110, 160, 50), bg=(200, 200, 200))).label == "unripe"
    assert classify_photo(jpeg((235, 130, 35), spots=[(330, 245, 30), (260, 265, 18)])).label == "mold"
    assert classify_photo(jpeg((128, 128, 128), bg=(128, 128, 128))).label == "none"


def test_photo_reply_is_honest():
    text = photo_reply(classify_photo(jpeg((240, 130, 20))))
    assert text.startswith("Ready to pick") and "colour check" in text


def photo_update(chat_id, data_bytes):
    file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(data_bytes)))
    size = SimpleNamespace(get_file=AsyncMock(return_value=file))
    msg = SimpleNamespace(photo=[size], caption=None, reply_text=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=msg)


def test_photo_handler_replies_with_label(data):
    u = photo_update(5, jpeg((240, 130, 20)))
    run(handlers(data).photo(u, context()))
    assert u.effective_message.reply_text.call_args.args[0].startswith("Ready to pick")


def test_photo_handler_unreadable_file(data):
    u = photo_update(5, b"not an image")
    run(handlers(data).photo(u, context()))
    assert "couldn't read that photo" in u.effective_message.reply_text.call_args.args[0]


def scan(scan_id, labels, demo=False):
    return {"id": scan_id, "taken_at": "2026-11-21T14:05:00-08:00", "source": "webcam", "model": "m",
            "image": None, "demo": demo,
            "fruits": [{"id": i, "label": l, "confidence": "high", "crop": None} for i, l in enumerate(labels, 1)]}


def test_mold_alert_text(data):
    msg = mold_alert(scan("a", ["ripe", "mold"], demo=True), data)
    assert "Possible mold spotted</b> on 1 orange in the scan at 2:05 PM" in msg.text
    assert "Demo data" in msg.text
    assert mold_alert(scan("b", ["ripe"]), data) is None


def test_watch_scans_alerts_only_on_new_mold_scans(data):
    h = handlers(data)
    h.state.subscribe(11, datetime.now().astimezone())
    store.append_scan(scan("first", ["mold"]))
    ctx = context()
    run(h.watch_scans(ctx))                      # baseline: no alert for what was already there
    ctx.bot.send_message.assert_not_called()
    store.append_scan(scan("second", ["ripe"]))
    run(h.watch_scans(ctx))                      # new scan, no mold: nothing
    ctx.bot.send_message.assert_not_called()
    store.append_scan(scan("third", ["mold", "mold"]))
    run(h.watch_scans(ctx))                      # new scan with mold: alert
    assert ctx.bot.send_message.call_args.args[0] == 11
    assert "2 oranges" in ctx.bot.send_message.call_args.args[1]
    run(h.watch_scans(ctx))                      # same scan again: no repeat
    assert ctx.bot.send_message.call_count == 1
