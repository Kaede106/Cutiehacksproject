"""The listen loop against a fake serial port: no hardware needed."""
from types import SimpleNamespace

from farm.sensors.bridge import find_port, listen
from farm.sensors.protocol import SoilCalibration

CAL = SoilCalibration(dry=600, wet=280)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class Done(Exception):
    """Script item that ends the test run."""


class FakeSerial:
    """readline() plays back (seconds_elapsed, bytes | Exception | Done) items."""

    def __init__(self, clock, state, script):
        self.clock, self.state, self.script = clock, state, list(script)
        self.closed = False

    def readline(self):
        dt, item = self.script.pop(0)
        self.clock.t += dt
        if item is Done:
            self.state.done = True
            return b""
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


def run(connections, *, every=10.0, port="COM9", detect=lambda: None, devices=lambda: ["COM9"]):
    """Run listen() over a list of connections (FakeSerial scripts, or exceptions to raise on open)."""
    clock, state = Clock(), SimpleNamespace(done=False, opened=[], written=[])
    pending = list(connections)

    def open_port(device, baud):
        state.opened.append(device)
        item = pending.pop(0)
        if isinstance(item, Exception):
            raise item
        ser = FakeSerial(clock, state, item)
        state.serials = getattr(state, "serials", []) + [ser]
        return ser

    listen(port, 9600, every, CAL, open_port=open_port, detect=detect, devices=devices,
           write=state.written.append, sleep=clock.sleep, monotonic=clock,
           now_iso=lambda: f"t={clock.t:g}", retry_s=3.0, stop=lambda: state.done)
    return state


def test_throttles_averages_and_reconnects():
    state = run([
        [
            (0, b"L=999;T=30.0\n"),        # t=0  tail of a line from before we connected: dropped
            (1, b"SOIL=440;T=20.0\n"),     # t=1  first reading is written at once
            (3, b"SOIL=360;T=21.0\n"),     # t=4  waits
            (3, b"SOIL=garbage\n"),        # t=7  malformed: skipped
            (2, b"SOIL=520;"),             # t=9  half a line (read timeout)...
            (1, b"T=23.0\r\n"),            # t=10 ...completed; still under 10 s since the last write
            (2, b"SOIL=440;T=22.0\n"),     # t=12 11 s since the last write: average of three
            (1, b"SOIL=280;T=30.0\n"),     # t=13 waits
            (1, OSError("unplugged")),     # t=14 board gone: the waiting reading is dropped
        ],
        PermissionError("Access is denied"),  # t=17 reopen fails (Serial Monitor open)
        [
            (0, b"# cutiefarm_sensors boot\n"),  # t=20
            (1, b"SOIL=280\n"),            # t=21 9 s since the last write: waits
            (2, b"SOIL=440\n"),            # t=23 writes the average of 280 and 440
            (0, Done),
        ],
    ])

    assert state.opened == ["COM9", "COM9", "COM9"]
    assert state.serials[0].closed and state.serials[1].closed
    assert state.written == [
        {"soil_moisture_pct": 50.0, "temperature_c": 20.0, "humidity_pct": None, "wind_ms": None,
         "raw": "SOIL=440;T=20.0", "taken_at": "t=1"},
        {"soil_moisture_pct": 50.0, "temperature_c": 22.0, "humidity_pct": None, "wind_ms": None,
         "raw": "SOIL=440;T=22.0", "taken_at": "t=12"},
        {"soil_moisture_pct": 75.0, "temperature_c": None, "humidity_pct": None, "wind_ms": None,
         "raw": "SOIL=440", "taken_at": "t=23"},
    ]


def test_silent_port_that_disappears_is_reopened():
    script = [(0, b"# boot\n")] + [(5, b"")] * 3  # 15 s of silence
    state = run([script, [(0, Done)]], devices=lambda: [])
    assert state.opened == ["COM9", "COM9"]
    assert state.written == []


def test_silent_port_still_present_is_kept():
    script = [(0, b"# boot\n")] + [(5, b"")] * 5 + [(0, b"SOIL=440\n"), (0, Done)]
    state = run([script])
    assert state.opened == ["COM9"]
    assert [r["soil_moisture_pct"] for r in state.written] == [50.0]


def test_waits_for_a_board_when_none_detected():
    answers = iter([None, None, "COM4"])
    state = run([[(0, b"# boot\n"), (1, b"SOIL=600;H=40\n"), (0, Done)]],
                port=None, detect=lambda: next(answers))
    assert state.opened == ["COM4"]
    assert state.written[0]["soil_moisture_pct"] == 0.0
    assert state.written[0]["humidity_pct"] == 40.0


def port(device, description, vid=None, manufacturer=None):
    return SimpleNamespace(device=device, description=description, vid=vid, pid=None,
                           manufacturer=manufacturer, product=None)


def test_find_port_prefers_arduino():
    ports = [
        port("COM3", "Standard Serial over Bluetooth link (COM3)"),
        port("COM5", "USB-SERIAL CH340 (COM5)", vid=0x1A86),
        port("COM7", "Arduino Uno (COM7)", vid=0x2341, manufacturer="Arduino LLC"),
    ]
    assert find_port(ports) == "COM7"
    assert find_port(ports[:2]) == "COM5"
    assert find_port(ports[:1]) is None
    assert find_port([]) is None
