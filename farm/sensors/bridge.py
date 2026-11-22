"""Serial side of the sensor bridge: port detection, line reading, the listen loop."""
from __future__ import annotations

import logging
import time
from statistics import fmean
from typing import Any, Callable, Iterable

from farm.common import store
from farm.sensors.protocol import KEYS, MAX_LINE, MalformedLine, SoilCalibration, parse_line, to_record

log = logging.getLogger("farm.sensors")

# USB vendor IDs: genuine Arduino boards, then the USB-serial chips clones use.
ARDUINO_VIDS = {0x2341, 0x2A03, 0x1B4F, 0x239A}  # Arduino, Arduino.org, SparkFun, Adafruit
CLONE_VIDS = {0x1A86, 0x0403, 0x10C4, 0x067B}  # CH340, FTDI, CP210x, PL2303
SILENCE_CHECK_S = 10.0


# ---------------------------------------------------------------- ports

def list_ports() -> list[Any]:
    from serial.tools import list_ports as lp

    return sorted(lp.comports(), key=lambda p: p.device)


def port_score(port: Any) -> int:
    """How likely a pyserial ListPortInfo is to be the sensor board (0 = no)."""
    text = f"{port.description or ''} {port.manufacturer or ''} {port.product or ''}".lower()
    if "bluetooth" in text:
        return 0
    if port.vid in ARDUINO_VIDS or "arduino" in text:
        return 3
    if port.vid in CLONE_VIDS or any(s in text for s in ("ch340", "ch341", "usb-serial", "usb serial", "ftdi", "cp210")):
        return 2
    return 0


def find_port(ports: Iterable[Any] | None = None) -> str | None:
    """Device name of the most Arduino-like serial port, or None."""
    candidates = [(port_score(p), p.device) for p in (list_ports() if ports is None else ports)]
    candidates = [c for c in candidates if c[0] > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])[1]


def open_serial(device: str, baud: int) -> Any:
    import serial

    ser = serial.Serial(device, baud, timeout=1)
    ser.reset_input_buffer()
    return ser


# ---------------------------------------------------------------- reading

class LineReader:
    """Turns readline() chunks into whole lines; pyserial returns partial lines on timeout."""

    def __init__(self, ser: Any):
        self.ser = ser
        self.buffer = b""

    def read(self) -> str | None:
        """One decoded line without its newline, or None if nothing complete arrived yet."""
        chunk = self.ser.readline()
        if not chunk:
            return None
        self.buffer += chunk
        if not self.buffer.endswith(b"\n"):
            if len(self.buffer) > MAX_LINE * 4:
                log.warning("dropping %d bytes with no newline (wrong baud rate?)", len(self.buffer))
                self.buffer = b""
            return None
        line, self.buffer = self.buffer, b""
        return line.decode("ascii", errors="replace").rstrip("\r\n")


def handle_line(line: str) -> dict[str, float | None] | None:
    """Parse a line, logging comments and malformed lines. None means skip it."""
    try:
        values = parse_line(line)
    except MalformedLine as e:
        log.warning("skipping malformed line %r: %s", line[:120], e)
        return None
    if values is None and line.strip():
        log.info("board: %s", line.strip())
    return values


# ---------------------------------------------------------------- averaging

class Averager:
    """Collects readings and writes their average at most every `every` seconds.

    The first reading is written straight away; later ones are averaged until
    `every` seconds have passed since the last write. A record's taken_at is
    the time of its newest sample, and raw is that sample's line.
    """

    def __init__(self, every: float, soil: SoilCalibration, *,
                 write: Callable[[dict[str, Any]], None] = store.append_sensors,
                 monotonic: Callable[[], float] = time.monotonic,
                 now_iso: Callable[[], str] = store.now_iso):
        self.every, self.soil, self.write = every, soil, write
        self.monotonic, self.now_iso = monotonic, now_iso
        self.samples: list[dict[str, float | None]] = []
        self.last_raw = ""
        self.last_taken = ""
        self.last_write: float | None = None

    def add(self, values: dict[str, float | None], raw: str) -> dict[str, Any] | None:
        self.samples.append(values)
        self.last_raw, self.last_taken = raw, self.now_iso()
        now = self.monotonic()
        if self.last_write is not None and now - self.last_write < self.every:
            return None
        averaged = {k: _mean([s[k] for s in self.samples]) for k in KEYS}
        count = len(self.samples)
        self.samples = []
        if all(v is None for v in averaged.values()):
            log.warning("%d reading(s) had no sensor values; nothing written", count)
            return None
        record = to_record(averaged, self.last_raw, self.soil)
        record["taken_at"] = self.last_taken
        self.write(record)
        self.last_write = now
        log.info("wrote %s (average of %d)", _summary(record), count)
        return record

    def discard(self) -> int:
        count, self.samples = len(self.samples), []
        return count


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return fmean(present) if present else None


def _summary(record: dict[str, Any]) -> str:
    def fmt(value: Any, unit: str) -> str:
        return "null" if value is None else f"{value}{unit}"

    return (f"soil={fmt(record['soil_moisture_pct'], '%')} T={fmt(record['temperature_c'], 'C')} "
            f"H={fmt(record['humidity_pct'], '%')} W={fmt(record['wind_ms'], 'm/s')}")


# ---------------------------------------------------------------- listen

def listen(port: str | None, baud: int, every: float, soil: SoilCalibration, *,
           open_port: Callable[[str, int], Any] = open_serial,
           detect: Callable[[], str | None] = find_port,
           devices: Callable[[], list[str]] = lambda: [p.device for p in list_ports()],
           write: Callable[[dict[str, Any]], None] = store.append_sensors,
           sleep: Callable[[float], None] = time.sleep,
           monotonic: Callable[[], float] = time.monotonic,
           now_iso: Callable[[], str] = store.now_iso,
           retry_s: float = 3.0,
           stop: Callable[[], bool] = lambda: False,
           water: Any = None) -> None:
    """Read the board forever, reconnecting whenever it goes away.

    `water` is an optional farm.irrigation_control.WaterQueue: watering commands
    from the bot are sent to the board while it is connected, and fail at once
    while it is not."""
    averager = Averager(every, soil, write=write, monotonic=monotonic, now_iso=now_iso)
    waiting_logged = False
    open_error_logged = False  # log a failing port once per outage, not every retry
    while not stop():
        device = port or detect()
        if device is None:
            if not waiting_logged:
                log.warning("no Arduino-like serial port found; waiting (or pass --port)")
                waiting_logged = True
            if water is not None:
                water.poll_unavailable("no board connected to the laptop")
            sleep(retry_s)
            continue
        try:
            ser = open_port(device, baud)
        except OSError as e:
            hint = " Is the Arduino IDE Serial Monitor open?" if isinstance(e, PermissionError) or "denied" in str(e).lower() else ""
            if not open_error_logged:
                log.warning("cannot open %s: %s.%s Retrying every %gs", device, e, hint, retry_s)
                open_error_logged = True
            if water is not None:
                water.poll_unavailable(f"cannot open the board's port {device}")
            sleep(retry_s)
            continue
        waiting_logged = open_error_logged = False
        log.info("connected to %s at %d baud", device, baud)
        try:
            _read_until_gone(ser, device, averager, devices, monotonic, stop, water)
        except OSError as e:
            log.warning("lost %s: %s", device, e)
        finally:
            try:
                ser.close()
            except Exception:
                pass
        dropped = averager.discard()
        if dropped:
            log.info("dropped %d unsaved reading(s) from before the disconnect", dropped)
        if not stop():
            sleep(retry_s)


def _read_until_gone(ser: Any, device: str, averager: Averager,
                     devices: Callable[[], list[str]], monotonic: Callable[[], float],
                     stop: Callable[[], bool], water: Any = None) -> None:
    reader = LineReader(ser)
    first = True
    last_data = monotonic()
    while not stop():
        if water is not None:
            water.poll(ser)
        line = reader.read()
        if line is None:
            if monotonic() - last_data > SILENCE_CHECK_S:
                # Some drivers just go quiet when the board is unplugged.
                if device not in devices():
                    raise OSError("port disappeared")
                last_data = monotonic()
            continue
        last_data = monotonic()
        if first:
            first = False  # may be the tail of a line sent before we connected
            log.debug("dropping first line after connect: %r", line)
            continue
        if water is not None and water.on_line(line):
            continue
        values = handle_line(line)
        if values is not None:
            averager.add(values, line.strip())
