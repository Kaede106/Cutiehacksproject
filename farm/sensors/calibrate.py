"""Interactive soil calibration: one dry reading, one wet reading, two numbers out."""
from __future__ import annotations

import time
from statistics import median
from typing import Any, Callable

from farm.sensors.bridge import LineReader, find_port, handle_line, open_serial

MIN_SAMPLES = 3
MIN_SPREAD = 50  # ADC counts between dry and wet; less means the probe is not reacting


def collect_soil(ser: Any, seconds: float, *, monotonic: Callable[[], float] = time.monotonic) -> list[float]:
    """Raw SOIL values the board sends during the next `seconds` seconds."""
    ser.reset_input_buffer()
    reader = LineReader(ser)
    reader.read()  # throw away a possibly partial first line
    samples: list[float] = []
    end = monotonic() + seconds
    while monotonic() < end:
        line = reader.read()
        if line is None:
            continue
        values = handle_line(line)
        if values and values["SOIL"] is not None:
            samples.append(values["SOIL"])
            print(f"    SOIL={values['SOIL']:.0f}", flush=True)
    return samples


def calibrate(port: str | None, baud: int, seconds: float, *,
              ask: Callable[[str], str] = input,
              open_port: Callable[[str, int], Any] = open_serial) -> tuple[float, float]:
    device = port or find_port()
    if device is None:
        raise SystemExit("No Arduino-like serial port found. Plug the board in, or pass --port (see `ports`).")
    print(f"Using {device} at {baud} baud. Close the Arduino IDE Serial Monitor first.")
    ser = open_port(device, baud)
    try:
        time.sleep(2)  # the Uno resets when the port opens
        results = []
        steps = [
            ("DRY", "Hold the probe in open air, or push it into completely dry soil."),
            ("WET", "Put the probe in a glass of water up to its line (keep the electronics dry), "
                    "or into soil you have just soaked."),
        ]
        for i, (name, how) in enumerate(steps, 1):
            ask(f"\nStep {i}/2, {name}: {how}\nPress Enter when it is in place...")
            print(f"  Reading for {seconds:g} s...")
            samples = collect_soil(ser, seconds)
            if len(samples) < MIN_SAMPLES:
                raise SystemExit(f"Only {len(samples)} SOIL readings arrived in {seconds:g} s. "
                                 "Is the sketch running and the baud rate right?")
            results.append(median(samples))
            print(f"  {name} = {results[-1]:.0f} (median of {len(samples)})")
    finally:
        ser.close()
    dry, wet = results
    print(f"\nCalibration: --soil-dry {dry:.0f} --soil-wet {wet:.0f}")
    if abs(dry - wet) < MIN_SPREAD:
        print(f"WARNING: dry and wet differ by under {MIN_SPREAD}. Check the wiring and repeat.")
    print(f"Run: python -m farm.sensors listen --soil-dry {dry:.0f} --soil-wet {wet:.0f}")
    return dry, wet
