"""Watering safety rules and the command queue (farm/irrigation_control.py). No hardware."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from farm import irrigation_control as ic

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 21, 14, 0, tzinfo=LA)
ON = ic.WaterSettings(auto=True)
OFF = ic.WaterSettings()


def soil(pct, minutes_ago=5, simulated=False):
    record = {"taken_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "soil_moisture_pct": pct}
    if simulated:
        record["simulated"] = True
    return record


def watering(minutes_ago, status=ic.DONE, seconds=8):
    return {"id": f"w{minutes_ago}", "taken_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "action": "water", "seconds": seconds, "status": status}


def check(settings=ON, *, soil_record=None, history=(), **kw):
    return ic.check(settings, now=NOW, soil=soil(28) if soil_record is None else soil_record,
                    history=list(history), **kw)


# ---------------------------------------------------------------- settings

def test_defaults_are_safe_and_auto_is_off():
    s = ic.settings_from_env({})
    assert s == ic.WaterSettings()
    assert (s.auto, s.seconds, s.max_seconds, s.cooldown_min, s.max_per_day) == (False, 8, 15, 60, 4)


@pytest.mark.parametrize("raw, auto", [("1", True), ("true", True), ("on", True), ("0", False), ("", False)])
def test_auto_water_switch(raw, auto):
    assert ic.settings_from_env({"AUTO_WATER": raw}).auto is auto


@pytest.mark.parametrize("env", [
    {"AUTO_WATER": "maybe"},
    {"MAX_WATER_SECONDS": "31"},  # above the absolute cap
    {"MAX_WATER_SECONDS": "0"},
    {"MAX_WATER_SECONDS": "7.5"},
    {"WATER_SECONDS": "20"},  # longer than MAX_WATER_SECONDS (15)
    {"WATER_COOLDOWN_MIN": "0"},
    {"MAX_WATERINGS_PER_DAY": "nan"},
    {"WET_ENOUGH_PCT": "101"},
])
def test_bad_settings_are_refused(env):
    with pytest.raises(ic.SettingsError):
        ic.settings_from_env(env)


def test_lower_max_seconds_lowers_the_default_run():
    assert ic.settings_from_env({"MAX_WATER_SECONDS": "5"}).seconds == 5


# ---------------------------------------------------------------- the rules

def test_dry_soil_waters_for_the_default_time():
    d = check()
    assert d.allowed and d.seconds == 8
    assert d.reason == "Watering for 8 s: soil at 28%."


def test_run_is_capped_at_max_seconds():
    assert check(seconds=60).seconds == 15
    assert check(ic.WaterSettings(auto=True, max_seconds=5, seconds=5), seconds=10).seconds == 5


def test_auto_mode_off_refuses_automatic_but_not_manual():
    assert not check(OFF).allowed
    assert "AUTO_WATER=0" in check(OFF).reason
    assert check(OFF, manual=True).allowed


def test_cooldown():
    d = check(history=[watering(20)])
    assert not d.allowed and not d.needs_override
    assert "20 min ago" in d.reason and "40 min more" in d.reason
    assert check(history=[watering(61)]).allowed
    # A manual request, even confirmed, respects the cooldown.
    assert not check(history=[watering(20)], manual=True, override=True).allowed


def test_cooldown_counts_pending_and_unconfirmed_but_not_failed_runs():
    assert not check(history=[watering(1, ic.PENDING)]).allowed  # a double tap queues one watering
    assert not check(history=[watering(10, ic.SENT)]).allowed
    assert not check(history=[watering(10, ic.NO_ACK)]).allowed  # it may have run
    assert check(history=[watering(10, ic.FAILED)]).allowed
    assert check(history=[watering(10, ic.EXPIRED)]).allowed
    # A command the bridge never picked up, too old to ever run, no longer blocks.
    assert check(history=[watering(10, ic.PENDING)]).allowed


def test_daily_cap():
    settings = ic.WaterSettings(auto=True, cooldown_min=1)
    four = [watering(m) for m in (200, 150, 100, 50)]
    d = check(settings, history=four)
    assert not d.allowed and "MAX_WATERINGS_PER_DAY=4" in d.reason
    assert not check(settings, history=four, manual=True, override=True).allowed
    assert check(settings, history=four[1:]).allowed
    # Yesterday's waterings don't count toward today.
    yesterday = [watering(m) for m in (15 * 60, 16 * 60, 17 * 60, 18 * 60)]
    assert check(settings, history=yesterday).allowed


def test_wet_soil_never_waters_automatically():
    d = check(soil_record=soil(72))
    assert not d.allowed and not d.needs_override
    assert "72%" in d.reason and "WET_ENOUGH_PCT" in d.reason
    assert check(soil_record=soil(60)).allowed  # at the threshold is still allowed


def test_wet_or_missing_soil_needs_a_confirmed_manual_override():
    for record in (soil(72), {}, soil(None), soil(30, minutes_ago=90)):
        d = check(soil_record=record, manual=True)
        assert not d.allowed and d.needs_override
        assert not check(soil_record=record).allowed  # automatic: never
        forced = check(soil_record=record, manual=True, override=True)
        assert forced.allowed and "as you confirmed" in forced.reason


def test_missing_soil_is_not_guessed():
    d = check(soil_record={})
    assert not d.allowed and d.soil_pct is None
    assert "no fresh soil moisture reading" in d.reason


def test_simulated_soil_is_labelled():
    d = check(soil_record=soil(28, simulated=True))
    assert d.allowed and d.soil_simulated and "(simulated)" in d.reason


# ---------------------------------------------------------------- queue files

@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    return tmp_path


def test_request_queues_once_then_cooldown_blocks(data):
    decision, command = ic.request(ON, now=NOW, requested_by="auto", reason="soil low", soil=soil(28))
    assert decision.allowed
    assert command["action"] == "water" and command["seconds"] == 8 and command["requested_by"] == "auto"
    assert ic.read_commands() == [command]
    again, none = ic.request(ON, now=NOW + timedelta(seconds=5), requested_by="chat:1", reason="",
                             manual=True, soil=soil(28))
    assert not again.allowed and none is None
    assert len(ic.read_commands()) == 1


def test_request_writes_nothing_when_soil_is_wet(data):
    decision, command = ic.request(ON, now=NOW, requested_by="auto", reason="x", soil=soil(80))
    assert command is None and not decision.allowed
    assert not (data / ic.COMMANDS_FILE).exists()


def test_statuses_use_the_latest_result():
    commands = [{"id": "a", "action": "water"}, {"id": "b", "action": "water"}, {"id": "c", "action": "x"}]
    results = [{"command_id": "a", "status": "sent"}, {"command_id": "a", "status": "done"}]
    assert [(c["id"], c["status"]) for c in ic.statuses(commands, results)] == [("a", "done"), ("b", "pending")]


class FakeSerial:
    def __init__(self, fail=False):
        self.written, self.fail = [], fail

    def write(self, data):
        if self.fail:
            raise OSError("port gone")
        self.written.append(data)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def queue(commands, results=None, **kw):
    out = [] if results is None else results
    clock = Clock()
    q = ic.WaterQueue(15, read=lambda: commands, read_done=lambda: list(out), write=out.append,
                      now=lambda: NOW, monotonic=clock, **kw)
    return q, out, clock


def cmd(id_="c1", seconds=8, minutes_ago=0.5, action="water"):
    return {"id": id_, "taken_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "action": action,
            "seconds": seconds, "reason": "test", "requested_by": "auto"}


def test_queue_round_trip_sends_water_and_records_the_ack():
    q, results, clock = queue([cmd()])
    ser = FakeSerial()
    q.poll(ser)
    assert ser.written == [b"WATER=8\n"]
    assert [(r["command_id"], r["status"]) for r in results] == [("c1", "sent")]
    q.poll(ser)
    assert ser.written == [b"WATER=8\n"]  # never sent twice
    assert q.on_line("#WATER_START 8") is True
    assert q.on_line("#WATER_DONE 8") is True
    assert [r["status"] for r in results] == ["sent", "done"]
    assert results[-1]["board_reply"] == "#WATER_DONE 8"
    assert "simulated" not in results[-1]


def test_commands_already_handled_are_not_resent_after_a_restart():
    q, results, _ = queue([cmd()], results=[{"command_id": "c1", "status": "done"}])
    ser = FakeSerial()
    q.poll(ser)
    assert ser.written == [] and len(results) == 1


def test_no_ack_after_the_run_and_grace():
    q, results, clock = queue([cmd()])
    q.poll(FakeSerial())
    clock.t = 8 + ic.ACK_GRACE_S - 1
    q.poll(FakeSerial())
    assert [r["status"] for r in results] == ["sent"]
    clock.t = 8 + ic.ACK_GRACE_S + 1
    q.poll(FakeSerial())
    assert [r["status"] for r in results] == ["sent", "no_ack"]
    assert "watering code" in results[-1]["detail"]


def test_board_refusal_is_a_failure():
    q, results, _ = queue([cmd()])
    q.poll(FakeSerial())
    q.on_line("#WATER_ERR busy")
    assert results[-1]["status"] == "failed" and "busy" in results[-1]["detail"]


def test_write_error_fails_the_command():
    q, results, _ = queue([cmd()])
    q.poll(FakeSerial(fail=True))
    assert results[-1]["status"] == "failed" and "port gone" in results[-1]["detail"]


@pytest.mark.parametrize("command, status", [
    (cmd(seconds=16), "failed"),  # above MAX_WATER_SECONDS: the bridge checks again
    (cmd(seconds=0), "failed"),
    (cmd(seconds=True), "failed"),
    (cmd(seconds="8"), "failed"),
    (cmd(action="drain"), "failed"),
    (cmd(minutes_ago=5), "expired"),  # queued while the bridge was down: never run late
    (cmd(minutes_ago=-10), "failed"),
])
def test_invalid_or_stale_commands_are_never_sent(command, status):
    q, results, _ = queue([command])
    ser = FakeSerial()
    q.poll(ser)
    assert ser.written == []
    assert [r["status"] for r in results] == [status]


def test_absolute_cap_even_if_constructed_higher():
    assert ic.WaterQueue(99, read=list, read_done=list, write=print).max_seconds == ic.ABSOLUTE_MAX_SECONDS


def test_no_board_fails_new_commands_at_once():
    q, results, _ = queue([cmd()])
    q.poll_unavailable("no board connected to the laptop")
    assert results[-1]["status"] == "failed" and results[-1]["detail"] == "no board connected to the laptop"


def test_simulated_mode_marks_results_and_runs_the_simulator():
    ran = []
    q, results, _ = queue([cmd()], on_water=ran.append)
    q.poll_simulated()
    assert ran == [8]
    assert results[-1]["status"] == "done" and results[-1]["simulated"] is True
    assert "nothing ran" in results[-1]["detail"]


def test_unreadable_queue_file_does_not_stop_the_bridge():
    def broken():
        raise PermissionError("locked")

    q = ic.WaterQueue(15, read=broken, read_done=list, write=print)
    ser = FakeSerial()
    q.poll(ser)
    assert ser.written == []


def test_other_lines_are_left_for_the_sensor_parser():
    q, _, _ = queue([])
    assert q.on_line("SOIL=440") is False
    assert q.on_line("# cutiefarm_sensors v1") is False
    assert q.on_line("#WATER_DONE 8") is True  # with nothing waiting: logged and consumed
