"""Watering commands through the bridge's listen loop and the simulator. No hardware."""
import json
import random
from datetime import datetime, timedelta, timezone

from farm import irrigation_control as ic
from farm.common import store
from farm.sensors.bridge import listen
from farm.sensors.protocol import SoilCalibration
from farm.sensors.simulate import Simulator, simulate

CAL = SoilCalibration(dry=600, wet=280)


def queue_command(seconds=8, id_="c1"):
    now = datetime.now(timezone.utc).astimezone()
    command = ic.new_command(seconds, "test", "chat:1", now)
    command["id"] = id_
    ic.append_command(command)
    return command


class Board:
    """A fake serial port: replays sensor lines and answers WATER=<n> like the snippet."""

    def __init__(self, lines, answer=True):
        self.lines, self.answer = list(lines), answer
        self.written = []
        self.done = False

    def readline(self):
        if not self.lines:
            self.done = True
            return b""
        return self.lines.pop(0)

    def write(self, data):
        self.written.append(data)
        n = data.decode().strip().split("=")[1]
        if self.answer:
            self.lines[:0] = [f"#WATER_START {n}\n".encode(), f"#WATER_DONE {n}\n".encode()]

    def flush(self):
        pass

    def close(self):
        pass


def run_listen(board, water):
    written = []
    listen("COM9", 9600, 10.0, CAL, open_port=lambda d, b: board, devices=lambda: ["COM9"],
           write=written.append, sleep=lambda s: None, stop=lambda: board.done, water=water)
    return written


def results(data):
    path = data / ic.RESULTS_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_listen_sends_water_and_records_the_board_ack(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    queue_command(8)
    board = Board([b"# boot\n", b"SOIL=440\n", b"SOIL=440\n"])
    written = run_listen(board, ic.WaterQueue(15))
    assert board.written == [b"WATER=8\n"]
    assert [(r["command_id"], r["status"]) for r in results(tmp_path)] == [("c1", "sent"), ("c1", "done")]
    assert all("simulated" not in r for r in results(tmp_path))
    # The board's watering lines are not sensor readings, and readings still flow.
    assert [r["soil_moisture_pct"] for r in written] == [50.0]


def test_listen_without_the_snippet_reports_no_ack(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    queue_command(8)
    ticks = iter(range(0, 10_000, 5))
    board = Board([b"# boot\n"] + [b"SOIL=440\n"] * 6, answer=False)  # the team's sketch ignores WATER=
    water = ic.WaterQueue(15, monotonic=lambda: next(ticks))
    run_listen(board, water)
    assert [r["status"] for r in results(tmp_path)] == ["sent", "no_ack"]


def test_listen_with_no_board_fails_the_command(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    queue_command(8)
    answers = iter([None, "COM4"])
    board = Board([b"# boot\n"])
    listen(None, 9600, 10.0, CAL, open_port=lambda d, b: board, detect=lambda: next(answers),
           devices=lambda: ["COM4"], write=lambda r: None, sleep=lambda s: None,
           stop=lambda: board.done, water=ic.WaterQueue(15))
    assert board.written == []
    assert [(r["status"], r["detail"]) for r in results(tmp_path)] == [("failed", "no board connected to the laptop")]


def test_simulate_marks_waterings_simulated_and_wets_the_soil(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    queue_command(8)
    simulate(3.0, CAL, count=2, seed=1, water=ic.WaterQueue(15), sleep=lambda s: None)
    (result,) = results(tmp_path)
    assert result["status"] == "done" and result["simulated"] is True
    assert all(r["simulated"] is True for r in store._read(store.SENSORS_FILE))


def test_simulated_watering_raises_simulated_moisture():
    sim = Simulator(CAL, random.Random(3))
    before = sim.moisture
    sim.water(8)
    assert sim.moisture == min(75.0, before + 24.0)


def test_simulate_without_a_queue_sleeps_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    sleeps = []
    simulate(10.0, CAL, count=2, seed=1, sleep=sleeps.append)
    assert sleeps == [10.0]


def test_old_commands_are_expired_not_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    old = datetime.now(timezone.utc).astimezone() - timedelta(minutes=30)
    ic.append_command(ic.new_command(8, "test", "auto", old))
    board = Board([b"# boot\n", b"SOIL=440\n"])
    run_listen(board, ic.WaterQueue(15))
    assert board.written == []
    assert [r["status"] for r in results(tmp_path)] == ["expired"]
