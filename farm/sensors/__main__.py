"""python -m farm.sensors {listen,ports,calibrate,simulate} --help"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys

from farm.sensors.protocol import DEFAULT_SOIL_DRY, DEFAULT_SOIL_WET, SoilCalibration

log = logging.getLogger("farm.sensors")


def duration(text: str) -> float:
    """'10', '10s', '2m' or '1h' as seconds."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", text.lower())
    if not match or float(match[1]) <= 0:
        raise argparse.ArgumentTypeError(f"not a duration: {text!r} (use 10s, 2m or 1h)")
    return float(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600}[match[2]]


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _add_soil(p: argparse.ArgumentParser) -> None:
    p.add_argument("--soil-dry", type=float, default=_env_float("CUTIEFARM_SOIL_DRY", DEFAULT_SOIL_DRY),
                   help=f"raw SOIL reading in dry air/soil (rough default {DEFAULT_SOIL_DRY}; "
                        "env CUTIEFARM_SOIL_DRY; get yours with `calibrate`)")
    p.add_argument("--soil-wet", type=float, default=_env_float("CUTIEFARM_SOIL_WET", DEFAULT_SOIL_WET),
                   help=f"raw SOIL reading in water/soaked soil (rough default {DEFAULT_SOIL_WET}; "
                        "env CUTIEFARM_SOIL_WET)")


def _soil(args: argparse.Namespace) -> SoilCalibration:
    try:
        soil = SoilCalibration(dry=args.soil_dry, wet=args.soil_wet)
    except ValueError as e:
        raise SystemExit(str(e))
    if (soil.dry, soil.wet) == (DEFAULT_SOIL_DRY, DEFAULT_SOIL_WET):
        log.warning("using rough default soil calibration (dry=%g, wet=%g); run `calibrate` for real numbers",
                    soil.dry, soil.wet)
    return soil


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farm.sensors", description="CutieFarm sensor bridge")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("listen", help="read the board and write sensors.jsonl")
    p.add_argument("--port", help="serial port, e.g. COM3 (default: auto-detect)")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--every", type=duration, default=60.0, help="write at most this often, averaging in between (default 60s)")
    _add_soil(p)

    sub.add_parser("ports", help="list serial ports")

    p = sub.add_parser("calibrate", help="measure the soil probe dry and wet")
    p.add_argument("--port")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--seconds", type=duration, default=12.0, help="how long to read each step (default 12s)")

    p = sub.add_parser("simulate", help='write fake readings marked "simulated": true, for demos')
    p.add_argument("--every", type=duration, default=10.0, help="default 10s")
    p.add_argument("--count", type=int, help="stop after this many readings (default: run until Ctrl+C)")
    p.add_argument("--seed", type=int)
    _add_soil(p)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        if args.command == "ports":
            return _ports()
        if args.command == "simulate":
            from farm.sensors.simulate import simulate

            simulate(args.every, SoilCalibration(args.soil_dry, args.soil_wet), count=args.count, seed=args.seed)
            return 0
        if args.command == "calibrate":
            from farm.sensors.calibrate import calibrate

            calibrate(args.port, args.baud, args.seconds)
            return 0
        from farm.sensors.bridge import listen

        listen(args.port, args.baud, args.every, _soil(args))
        return 0
    except KeyboardInterrupt:
        return 130
    except ModuleNotFoundError as e:
        if e.name == "serial":
            raise SystemExit("pyserial is missing: use farm\\sensors\\.venv\\Scripts\\python (see README)")
        raise


def _ports() -> int:
    from farm.sensors.bridge import find_port, list_ports, port_score

    ports = list_ports()
    if not ports:
        print("No serial ports found. Is the board plugged in (with a data cable, not a charge-only one)?")
        return 0
    best = find_port(ports)
    for port in ports:
        vidpid = f"{port.vid:04X}:{port.pid:04X}" if port.vid is not None else "----:----"
        mark = "  <- will be used" if port.device == best else ("  (likely a board)" if port_score(port) else "")
        print(f"{port.device:8} {vidpid}  {port.description}{mark}")
    if best is None:
        print("None of these looks like an Arduino; pass --port explicitly if yours is listed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
