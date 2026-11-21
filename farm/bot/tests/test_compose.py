import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from farm.bot.compose import MAX_PHOTOS, compose, to_plain
from farm.bot.fixtures import FIXTURES

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 21, 9, 0, 30, tzinfo=LA)


def scan(labels, *, age=timedelta(seconds=20), model="color-heuristic-v1", conf=None, crops=True, **extra):
    fruits = [
        {"id": i, "label": lab, "confidence": (conf or {}).get(i, "high"), "bbox": [0, 0, 1, 1],
         "crop": f"scans/s-{i}.jpg" if lab == "mold" and crops else None}
        for i, lab in enumerate(labels, start=1)
    ]
    record = {"id": "s", "taken_at": (NOW - age).isoformat(timespec="seconds"), "source": "webcam",
              "model": model, "image": "scans/s.jpg", "fruits": fruits,
              "summary": {k: labels.count(k) for k in ("unripe", "ripening", "ripe", "mold")}}
    record.update(extra)
    return record


def sensors(*, age=timedelta(minutes=1), **values):
    base = {"taken_at": (NOW - age).isoformat(timespec="seconds"), "soil_moisture_pct": 41.0,
            "temperature_c": 22.4, "humidity_pct": 55.0, "wind_ms": 3.2}
    base.update(values)
    return base


def plain(message):
    return to_plain(message.text)


def first_line(message):
    return plain(message).splitlines()[0]


def test_nonfinite_sensor_values_are_omitted():
    record = sensors(temperature_c=float("inf"), humidity_pct=float("nan"), wind_ms=float("-inf"))
    text = plain(compose(None, record, NOW))
    assert "soil moisture 41%" in text
    assert " °C" not in text and "humidity" not in text and "wind" not in text


# --- counts and what to do ---------------------------------------------------


def test_landing_page_example_wording():
    m = compose(scan(["ripe"] * 3 + ["ripening"] * 5 + ["mold"]), None, NOW)
    assert first_line(m) == "3 ready to pick, 5 ripening, 1 possible mold (photo attached): remove it today."
    assert "Remove the fruit with possible mold today, before the mold spreads." in plain(m)
    assert "Pick the 3 oranges that are ready." in plain(m)
    assert "Check the 5 ripening ones again in a few days." in plain(m)
    assert [p.path for p in m.photos] == ["scans/s-9.jpg"]
    assert "fruit 9 (high confidence)" in m.photos[0].caption


def test_ripe_heavy_lists_actions_in_order_of_urgency():
    m = compose(scan(["ripe"] * 6 + ["ripening"] * 2 + ["unripe"]), None, NOW)
    lines = plain(m).splitlines()
    assert lines[0] == "6 ready to pick, 2 ripening, 1 unripe."
    assert lines[2:5] == ["Pick the 6 oranges that are ready.", "Check the 2 ripening ones again in a few days.",
                          "Leave the unripe one on the tree."]
    assert m.photos == ()


def test_singular_forms():
    text = plain(compose(scan(["ripe", "ripening", "unripe"]), None, NOW))
    assert "Pick the orange that is ready." in text
    assert "Check the ripening one again in a few days." in text
    assert "Leave the unripe one on the tree." in text


def test_everything_unripe_says_nothing_to_pick():
    m = compose(scan(["unripe"] * 7), None, NOW)
    assert first_line(m) == "Nothing to pick today."
    assert "Leave the 7 unripe ones on the tree." in plain(m)


def test_ripening_without_ripe_says_nothing_to_pick():
    m = compose(scan(["ripening"] * 2 + ["unripe"]), None, NOW)
    assert first_line(m) == "Nothing to pick today."
    assert "Check the 2 ripening ones again in a few days." in plain(m)


def test_mold_without_ripe_says_nothing_ready():
    m = compose(scan(["mold", "mold", "unripe"]), None, NOW)
    assert first_line(m) == "1 unripe, 2 possible mold (photos attached): remove them today."
    assert "Remove the 2 fruits with possible mold today" in plain(m)
    assert "Nothing is ready to pick yet." in plain(m)


def test_low_confidence_mold_asks_to_check_by_eye():
    m = compose(scan(["mold"], conf={1: "low"}), None, NOW)
    assert "check by eye first" in plain(m)
    assert "check by eye" not in plain(compose(scan(["mold"]), None, NOW))


def test_counts_fall_back_to_fruits_without_summary():
    record = scan(["ripe", "ripe", "mold"])
    del record["summary"]
    assert first_line(compose(record, None, NOW)).startswith("2 ready to pick, 1 possible mold")


def test_bad_summary_values_are_ignored():
    record = scan(["ripe"], summary={"ripe": 2, "mold": -1, "unripe": "3", "ripening": True})
    assert first_line(compose(record, None, NOW)) == "2 ready to pick."


# --- photos -----------------------------------------------------------------


def test_photo_only_promised_when_it_can_be_sent():
    m = compose(scan(["ripe", "mold"]), None, NOW, photo_ok=lambda p: False)
    assert m.photos == ()
    assert first_line(m) == "1 ready to pick, 1 possible mold: remove it today."


def test_photos_are_capped_and_most_confident_first():
    record = scan(["mold"] * 5, conf={1: "low", 2: "medium", 3: "high", 4: "low", 5: "high"})
    m = compose(record, None, NOW)
    assert len(m.photos) == MAX_PHOTOS == 3
    assert [p.path for p in m.photos] == ["scans/s-3.jpg", "scans/s-5.jpg", "scans/s-2.jpg"]
    assert "5 possible mold (photos of 3 attached)" in first_line(m)


def test_whole_scan_is_sent_when_no_crop_exists():
    m = compose(scan(["mold", "mold"], crops=False), None, NOW)
    assert [p.path for p in m.photos] == ["scans/s.jpg"]
    assert "2 possible mold (photo attached)" in first_line(m)


def test_no_photo_at_all_without_crop_or_image():
    record = scan(["mold"], crops=False, image=None)
    m = compose(record, None, NOW)
    assert m.photos == ()
    assert "attached" not in plain(m)


# --- missing, stale or empty scans -------------------------------------------


def test_no_scan_ever():
    m = compose(None, None, NOW)
    text = plain(m)
    assert first_line(m) == "No scan in the last 24 hours."
    assert "There are no scans yet." in text
    assert "webcam is connected" in text and "camera program" in text and "/status" in text
    assert m.photos == ()


def test_stale_scan_names_when_the_last_one_was():
    m = compose(scan(["ripe", "mold"], age=timedelta(days=2)), None, NOW)
    assert first_line(m) == "No scan in the last 24 hours."
    assert "The last one was on Thursday, Nov 19 at 9:00 AM." in plain(m)
    assert m.photos == ()  # an old mold photo is not today's news


def test_scan_just_under_24h_still_counts():
    m = compose(scan(["ripe"], age=timedelta(hours=23, minutes=59)), None, NOW)
    assert first_line(m) == "1 ready to pick."
    assert "Scan: yesterday at 9:01 AM." in plain(m)


def test_unreadable_scan_time_is_treated_as_no_scan():
    m = compose(scan(["ripe"], taken_at="sometime"), None, NOW)
    assert "The last scan has no readable time." in plain(m)


def test_naive_scan_time_is_read_as_local():
    m = compose(scan(["ripe"], taken_at="2026-11-21T08:30:00"), None, NOW)
    assert "Scan: today at 8:30 AM." in plain(m)


def test_scan_command_is_shown_and_escaped():
    m = compose(None, None, NOW, scan_command="run <scan> & go")
    assert "<code>run &lt;scan&gt; &amp; go</code>" in m.text


def test_scan_with_no_fruit():
    m = compose(scan([]), None, NOW)
    text = plain(m)
    assert first_line(m) == "The last scan (today at 9:00 AM) found no oranges."
    assert "camera points at the fruit" in text
    assert "Scan:" not in text  # the time is already in the first line
    assert "colour check" in text


# --- sensors ----------------------------------------------------------------


def test_fresh_sensor_line():
    text = plain(compose(scan(["ripe"]), sensors(), NOW))
    assert "Sensors at 8:59 AM: soil moisture 41%, 22.4 °C (72 °F), humidity 55%, wind 3.2 m/s." in text


def test_simulated_sensors_say_so():
    assert "Sensors (simulated) at" in plain(compose(scan(["ripe"]), sensors(simulated=True), NOW))
    assert "simulated" not in plain(compose(scan(["ripe"]), sensors(simulated=False), NOW))


def test_null_and_bad_sensor_values_are_skipped_silently():
    text = plain(compose(scan(["ripe"]), sensors(wind_ms=None, humidity_pct=True, soil_moisture_pct="41"), NOW))
    line = next(l for l in text.splitlines() if l.startswith("Sensors"))
    assert line == "Sensors at 8:59 AM: 22.4 °C (72 °F)."


def test_all_null_sensors_give_no_line():
    nulls = dict(soil_moisture_pct=None, temperature_c=None, humidity_pct=None, wind_ms=None)
    assert "Sensors" not in plain(compose(scan(["ripe"]), sensors(**nulls), NOW))


def test_old_sensor_reading_is_left_out():
    assert "Sensors" not in plain(compose(scan(["ripe"]), sensors(age=timedelta(minutes=61)), NOW))
    assert "Sensors" in plain(compose(scan(["ripe"]), sensors(age=timedelta(minutes=59)), NOW))


def test_fresh_sensors_still_shown_when_scan_is_stale():
    assert "Sensors at" in plain(compose(None, sensors(), NOW))


# --- honesty and formatting ---------------------------------------------------


def test_colour_check_line_only_for_the_heuristic():
    assert "colour check" in plain(compose(scan(["ripe"]), None, NOW))
    assert "colour check" not in plain(compose(scan(["ripe"], model="orange-cnn-v1"), None, NOW))


def test_data_text_is_escaped_in_captions():
    record = scan(["mold"])
    record["fruits"][0]["id"] = "<b>x</b>&"
    caption = compose(record, None, NOW).photos[0].caption
    assert "&lt;b&gt;x&lt;/b&gt;&amp;" in caption


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_fixture_is_plain_valid_telegram_html(name):
    from farm.bot.irrigation import IrrigationConfig, advise

    fx = FIXTURES[name](NOW)
    advice = advise(fx.history, fx.weather, NOW.date(), IrrigationConfig(), now=NOW)
    m = compose(fx.scan, fx.sensors, NOW, irrigation=advice)
    for text in [m.text] + [p.caption for p in m.photos]:
        assert "!" not in text
        assert all(ord(c) < 0x2190 for c in text), "no emoji or pictographs"
        tags = re.findall(r"</?([a-z]+)[^>]*>", text)
        assert set(tags) <= {"b", "i", "code"}
        stripped = re.sub(r"</?(b|i|code)>", "", text)
        assert "<" not in stripped and ">" not in stripped
        assert not re.search(r"&(?!amp;|lt;|gt;|quot;)", stripped)
    assert len(m.text) < 4096


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        compose(None, None, datetime(2026, 11, 21, 9, 0))


def test_times_shown_in_the_timezone_of_now():
    record = scan(["ripe"], taken_at="2026-11-21T17:00:00+00:00")  # 9:00 AM in Los Angeles
    assert "Scan: today at 9:00 AM." in plain(compose(record, None, NOW))


def test_to_plain():
    assert to_plain("<b>a &amp; b</b> <code>&lt;x&gt;</code>") == "a & b <x>"
