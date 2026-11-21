"""CutieFarm hub: start every laptop-side part with one command and watch them.

    python -m farm                     bot + sensor bridge (+ vision, if VISION_COMMAND is set)
    python -m farm --simulate-sensors  same, with simulated sensor readings instead of the board
    python -m farm --no-sensors        bot only (plus vision, if set)
    python -m farm status              print the status once and exit

The parts still never talk to each other: they share the data folder described in
farm/CONTRACT.md. The hub only starts them, restarts any that crash, sends each one's output
to <data folder>/logs/<part>.log and shows one status screen.

Settings come from farm/bot/.env (the same file the bot reads), so every part uses the same
CUTIEFARM_DATA folder:
  SENSORS_ARGS    extra arguments for the bridge, e.g. "--port COM3 --soil-dry 610 --soil-wet 290"
  VISION_COMMAND  the command that runs the camera program, e.g. "python vision/run.py --every 60"
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_RESTARTS = 5  # per part within RESTART_WINDOW seconds, then it is marked failed
RESTART_WINDOW = 120
CONFIG_ERROR = 2  # exit code the bot and the bridge use for "fix the settings first"


def _load_env() -> None:
    from farm.bot.config import load_env_file
    load_env_file()


@dataclass
class Part:
    name: str
    command: list[str]
    log_path: Path
    process: subprocess.Popen | None = None
    started: float = 0.0
    restarts: list[float] = field(default_factory=list)
    state: str = "starting"  # running | restarting | failed | stopped
    note: str = ""

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "a", encoding="utf-8")
        log.write(f"\n--- started {datetime.now():%Y-%m-%d %H:%M:%S}: {' '.join(self.command)}\n")
        log.flush()
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        if self.name in ("sensors", "vision"):
            env.pop("TELEGRAM_BOT_TOKEN", None)
            env.pop("OPENAI_API_KEY", None)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(self.command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        env=env, creationflags=flags)
        log.close()  # the child keeps its own handle
        self.started = time.monotonic()
        self.state, self.note = "running", ""

    def check(self) -> None:
        """Restart the part if it died, unless it keeps dying or needs its settings fixed."""
        if self.process is None or self.state in ("failed", "stopped"):
            return
        code = self.process.poll()
        if code is None:
            return
        now = time.monotonic()
        if code == CONFIG_ERROR:
            self.state, self.note = "failed", f"settings problem, see {self.log_path.name}"
            return
        self.restarts = [t for t in self.restarts if now - t < RESTART_WINDOW] + [now]
        if len(self.restarts) > MAX_RESTARTS:
            self.state, self.note = "failed", f"crashed {MAX_RESTARTS} times, see {self.log_path.name}"
            return
        self.state, self.note = "restarting", f"exited with code {code}"
        self.start()
        self.note = f"restarted after exit code {code}"

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.state = "stopped"


def last_line(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = [l for l in f.read().decode("utf-8", "replace").splitlines() if l.strip()]
        return lines[-1][:110] if lines else ""
    except OSError:
        return ""


def _age(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        seconds = (datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return "unknown"
    if seconds < 90:
        return f"{int(seconds)} s ago"
    if seconds < 5400:
        return f"{int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h ago"
    return f"{int(seconds // 86400)} days ago"


def data_lines() -> list[str]:
    """What the shared data folder says right now."""
    from farm.common import store
    folder = store.data_dir()
    scan = store.latest_scan(max_age=None)
    sensors = store.latest_sensors(max_age=None)
    lines = [f"Data folder   {folder}"]
    if scan:
        s = scan.get("summary") or {}
        tag = " (demo)" if scan.get("demo") else ""
        lines.append(f"Last scan     {_age(scan.get('taken_at'))}{tag}: {s.get('ripe', 0)} ready, "
                     f"{s.get('ripening', 0)} ripening, {s.get('unripe', 0)} unripe, {s.get('mold', 0)} possible mold")
    else:
        lines.append("Last scan     none yet")
    if sensors:
        tag = " (simulated)" if sensors.get("simulated") else ""
        vals = [f"{k} {sensors[k]}" for k in ("soil_moisture_pct", "temperature_c", "humidity_pct", "wind_ms")
                if sensors.get(k) is not None]
        lines.append(f"Last sensors  {_age(sensors.get('taken_at'))}{tag}: {', '.join(vals) or 'no values'}")
    else:
        lines.append("Last sensors  none yet")
    try:
        state = json.loads((folder / "bot_state.json").read_text(encoding="utf-8"))
        chats = state.get("chats", state.get("subscribers", []))
        lines.append(f"Subscribers   {len(chats)} chat(s) get the {os.environ.get('DAILY_AT', '09:00')} message")
    except (OSError, ValueError):
        lines.append("Subscribers   none yet (send /start to the bot)")
    return lines


def render(parts: list[Part]) -> str:
    out = [f"CutieFarm hub   {datetime.now():%H:%M:%S}   Ctrl+C stops everything", ""]
    for p in parts:
        up = ""
        if p.state == "running" and p.process:
            up = f"up {int(time.monotonic() - p.started)} s, pid {p.process.pid}"
        out.append(f"  {p.name:<8} {p.state:<10} {up:<24} {p.note}")
        tail = last_line(p.log_path)
        if tail:
            out.append(f"           {tail}")
    out.append("")
    out.extend(data_lines())
    return "\n".join(out)


def build_parts(args: argparse.Namespace) -> list[Part]:
    from farm.common import store
    logs = store.data_dir() / "logs"
    py = sys.executable
    parts = [Part("bot", [py, "-m", "farm.bot", "run"], logs / "bot.log")]
    if args.simulate_sensors:
        parts.append(Part("sensors", [py, "-m", "farm.sensors", "simulate", "--every", "30s"], logs / "sensors.log"))
    elif not args.no_sensors:
        extra = shlex.split(os.environ.get("SENSORS_ARGS", ""), posix=os.name != "nt")
        parts.append(Part("sensors", [py, "-m", "farm.sensors", "listen", *extra], logs / "sensors.log"))
    vision = os.environ.get("VISION_COMMAND", "").strip()
    if vision:
        parts.append(Part("vision", shlex.split(vision, posix=os.name != "nt"), logs / "vision.log"))
    return parts


def run(args: argparse.Namespace) -> int:
    parts = build_parts(args)
    for p in parts:
        p.start()
    if os.name == "nt":
        os.system("")  # turn on ANSI escape codes in the Windows console
    try:
        while True:
            for p in parts:
                p.check()
            try:
                screen = render(parts)
            except Exception as exc:
                screen = f"CutieFarm hub: could not render status ({type(exc).__name__})."
            sys.stdout.write("\x1b[2J\x1b[H" + screen + "\n")
            sys.stdout.flush()
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        for p in parts:
            p.stop()
        print("\nStopped all parts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m farm", description="Start and watch every CutieFarm part.")
    parser.add_argument("command", nargs="?", choices=["run", "status"], default="run")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--simulate-sensors", action="store_true", help="simulated readings instead of the board")
    group.add_argument("--no-sensors", action="store_true", help="don't start the sensor bridge")
    args = parser.parse_args(argv)
    _load_env()
    if args.command == "status":
        try:
            print("\n".join(data_lines()))
        except Exception as exc:
            print(f"CutieFarm hub: could not read status ({type(exc).__name__}).")
            return 1
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
