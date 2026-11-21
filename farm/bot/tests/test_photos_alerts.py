import asyncio
import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image, ImageDraw
from telegram.error import Forbidden

from farm.bot import photo
from farm.bot.app import MAX_PHOTO_BYTES
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
    assert classify_photo(jpeg((222, 195, 35), bg=(200, 200, 200))).label == "ripening"
    spotted = classify_photo(jpeg((235, 130, 35), spots=[(330, 245, 30), (260, 265, 18)]))
    assert spotted.label == "ripe"
    assert set(spotted.scores) == set(store.LABELS)
    assert classify_photo(jpeg((128, 128, 128), bg=(128, 128, 128))).label == "none"


def test_photo_reply_is_honest():
    text = photo_reply(classify_photo(jpeg((240, 130, 20))))
    assert text.startswith("Ready to pick") and "colour check" in text


def test_photo_requests_jpeg_draft_before_exif_transpose(monkeypatch):
    transpose = photo.ImageOps.exif_transpose
    seen = []

    def check_size(image):
        seen.append(image.size)
        return transpose(image)

    monkeypatch.setattr(photo.ImageOps, "exif_transpose", check_size)
    data = io.BytesIO()
    Image.new("RGB", (2048, 2048), (240, 130, 20)).save(data, "JPEG")
    classify_photo(data.getvalue())
    assert seen == [(512, 512)]
    assert Image.MAX_IMAGE_PIXELS == 25_000_000


def photo_size(data_bytes, width=300, height=300, file_size=None):
    file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(data_bytes)))
    return SimpleNamespace(width=width, height=height, file_size=file_size, get_file=AsyncMock(return_value=file))


def photo_update(chat_id, *sizes):
    u = update(chat_id)
    u.effective_message.photo = sizes
    u.effective_message.caption = None
    return u


def test_photo_handler_replies_with_label(data):
    u = photo_update(5, photo_size(jpeg((240, 130, 20))))
    run(handlers(data).photo(u, context()))
    assert u.effective_message.reply_text.call_args.args[0].startswith("Ready to pick")


def test_photo_handler_unreadable_file(data):
    u = photo_update(5, photo_size(b"not an image"))
    run(handlers(data).photo(u, context()))
    assert "couldn't read that photo" in u.effective_message.reply_text.call_args.args[0]


@pytest.mark.parametrize("widths", [(640, 255, 256), (128, 64, 200)])
def test_photo_handler_chooses_smallest_suitable_or_largest_available(data, widths):
    jpeg_data = jpeg((240, 130, 20))
    sizes = [photo_size(jpeg_data, width=w, height=300) for w in widths]
    u = photo_update(5, *sizes)
    run(handlers(data).photo(u, context()))
    for size in sizes[:2]:
        size.get_file.assert_not_called()
    sizes[2].get_file.assert_awaited_once()


@pytest.mark.parametrize("file_size", [MAX_PHOTO_BYTES + 1, None])
def test_photo_handler_rejects_oversize_photos(data, file_size):
    size = photo_size(bytearray(MAX_PHOTO_BYTES + 1), file_size=file_size)
    u = photo_update(5, size)
    run(handlers(data).photo(u, context()))
    assert size.get_file.await_count == (0 if file_size else 1)
    assert "5 MB" in u.effective_message.reply_text.await_args.args[0]


def scan(scan_id, ripe, **extra):
    return {"id": scan_id, "taken_at": "2026-11-21T14:05:00-08:00", "source": "webcam", "model": "m",
            "fruits": [{"label": "ripe"} for _ in range(ripe)], **extra}


def subscribed(data):
    h = handlers(data)
    h.state.subscribe(11, datetime.now().astimezone())
    return h


def test_watch_scans_is_quiet_at_startup(data):
    store.append_scan(scan("older", 1))
    store.append_scan(scan("at-startup", 3))
    h, ctx = subscribed(data), context()
    run(h.watch_scans(ctx))
    ctx.bot.send_message.assert_not_called()


def test_ripe_increase_alerts_once_per_scan(data):
    h, ctx = subscribed(data), context()
    store.append_scan(scan("first", 3))
    run(h.watch_scans(ctx))
    store.append_scan(scan("second", 5, demo=True))
    run(h.watch_scans(ctx))
    run(h.watch_scans(ctx))
    ctx.bot.send_message.assert_awaited_once()
    chat_id, message = ctx.bot.send_message.await_args.args
    assert chat_id == 11
    assert "2 more oranges are ready to pick (5 in total)" in message
    assert "Demo data" in message


def test_no_alert_until_ripe_count_increases_again(data):
    h, ctx = subscribed(data), context()
    store.append_scan(scan("first", 3))
    run(h.watch_scans(ctx))
    store.append_scan(scan("same", 3))
    store.append_scan(scan("fewer", 1))
    run(h.watch_scans(ctx))
    ctx.bot.send_message.assert_not_called()

    store.append_scan(scan("more", 2))
    store.append_scan(scan("equal", 2))
    run(h.watch_scans(ctx))
    ctx.bot.send_message.assert_awaited_once()
    assert "1 more orange is ready to pick (2 in total)" in ctx.bot.send_message.await_args.args[1]


@pytest.mark.parametrize("image", ["scans/whole.jpg", "scans/missing.jpg", "../private.jpg", None])
def test_alert_attaches_only_an_existing_scan_image(data, image):
    (data / "scans").mkdir()
    whole = data / "scans" / "whole.jpg"
    whole.write_bytes(b"\xff\xd8")
    (data / "scans" / "crop.jpg").write_bytes(b"\xff\xd8")
    (data.parent / "private.jpg").write_bytes(b"\xff\xd8")
    h, ctx = subscribed(data), context()
    store.append_scan(scan("first", 0))
    run(h.watch_scans(ctx))
    newer = scan("second", 1, image=image)
    newer["fruits"].extend([{"label": "mold", "crop": "scans/crop.jpg"}, None])
    store._append(store.SCANS_FILE, newer)
    run(h.watch_scans(ctx))
    ctx.bot.send_message.assert_awaited_once()
    if image == "scans/whole.jpg":
        ctx.bot.send_photo.assert_awaited_once()
        assert ctx.bot.send_photo.await_args.kwargs["photo"] == whole.resolve()
    else:
        ctx.bot.send_photo.assert_not_called()


def test_ripe_alert_unsubscribes_blocked_chats_and_continues(data, caplog):
    h, ctx = subscribed(data), context()
    for chat_id in (12, 13):
        h.state.subscribe(chat_id, datetime.now().astimezone())
    store.append_scan(scan("first", 0))
    run(h.watch_scans(ctx))
    store.append_scan(scan("second", 1))
    ctx.bot.send_message.side_effect = [Forbidden("blocked"), RuntimeError("failed"), None]
    run(h.watch_scans(ctx))
    assert [call.args[0] for call in ctx.bot.send_message.await_args_list] == [11, 12, 13]
    assert h.state.chats() == [12, 13]
    assert "Could not send the ripe alert to chat 12" in caplog.text


def test_watch_scans_catches_alert_processing_failure(data, monkeypatch, caplog):
    h, ctx = subscribed(data), context()
    store.append_scan(scan("first", 1))
    run(h.watch_scans(ctx))
    store.append_scan(scan("second", 2))

    def bad_alert(*args):
        raise ValueError("malformed scan")

    monkeypatch.setattr("farm.bot.app.ripe_alert", bad_alert)
    run(h.watch_scans(ctx))
    assert "Could not check scans for ripe alerts" in caplog.text
    ctx.bot.send_message.assert_not_called()
