"""Watering commands: the command queue, its results, and the safety rules.

The bot never touches the serial port. It appends a command to `irrigation.jsonl`
in the data folder; the sensor bridge, the only process that holds the Arduino's
port, sends `WATER=<seconds>` to the board and appends what happened to
`irrigation_results.jsonl`. Both formats are in farm/CONTRACT.md.

Every rule that decides whether the pump may run lives here, so the bot's
automatic job and its /water_now command apply exactly the same checks:

- a run lasts at most MAX_WATER_SECONDS (default 15; never more than 30);
- at least WATER_COOLDOWN_MIN minutes (default 60) between waterings;
- at most MAX_WATERINGS_PER_DAY waterings (default 4) per calendar day;
- no watering when the latest soil reading is above WET_ENOUGH_PCT (default 60)
  or there is no fresh soil reading, unless a person asked for it with /water_now
  and confirmed "Water anyway";
- automatic watering is off unless AUTO_WATER=1.

The bridge checks the length again, and the board has its own hard cap.
"""
from __future__ import annotations

import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from farm.common import store

COMMANDS_FILE = "irrigation.jsonl"
RESULTS_FILE = "irrigation_results.jsonl"

ABSOLUTE_MAX_SECONDS = 30  # no setting can go above this; the board refuses longer runs too
COMMAND_TTL = timedelta(minutes=2)  # the bridge never runs a command older than this
ACK_GRACE_S = 10.0  # after the run should have ended, wait this long for #WATER_DONE
SOIL_FRESH = timedelta(hours=1)  # an older soil reading counts as missing

# Result statuses (farm/CONTRACT.md). A command with no result yet is "pending".
PENDING = "pending"
SENT = "sent"  # written to the board; waiting for #WATER_DONE
DONE = "done"  # the board confirmed, or the simulator ran it ("simulated": true)
NO_ACK = "no_ack"  # sent, but the board never confirmed: it may or may not have run
FAILED = "failed"  # not run: no board, a write error, or the board refused it
EXPIRED = "expired"  # the bridge saw it too late and did not run it
# Statuses that count toward the cooldown and the daily cap: the pump ran, or may have.
COUNTED = (PENDING, SENT, DONE, NO_ACK)

_lock = threading.Lock()


class SettingsError(ValueError):
    """A watering setting is wrong. The message is one line, safe to print."""


@dataclass(frozen=True)
class WaterSettings:
    auto: bool = False  # AUTO_WATER
    seconds: int = 8  # WATER_SECONDS: how long one watering runs
    max_seconds: int = 15  # MAX_WATER_SECONDS
    cooldown_min: float = 60.0  # WATER_COOLDOWN_MIN
    max_per_day: int = 4  # MAX_WATERINGS_PER_DAY
    wet_enough_pct: float = 60.0  # WET_ENOUGH_PCT
    check_every_min: float = 10.0  # AUTO_WATER_EVERY_MIN


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"", "0", "false", "no", "off"}


def settings_from_env(env: Mapping[str, str]) -> WaterSettings:
    d = WaterSettings()
    auto_raw = (env.get("AUTO_WATER") or "").strip().lower()
    if auto_raw not in _TRUE | _FALSE:
        raise SettingsError(f"AUTO_WATER must be 0 or 1, not {auto_raw!r}.")
    max_seconds = int(_number(env, "MAX_WATER_SECONDS", d.max_seconds, 1, ABSOLUTE_MAX_SECONDS, whole=True))
    return WaterSettings(
        auto=auto_raw in _TRUE,
        seconds=int(_number(env, "WATER_SECONDS", min(d.seconds, max_seconds), 1, max_seconds, whole=True)),
        max_seconds=max_seconds,
        cooldown_min=_number(env, "WATER_COOLDOWN_MIN", d.cooldown_min, 1, 1440),
        max_per_day=int(_number(env, "MAX_WATERINGS_PER_DAY", d.max_per_day, 1, 48, whole=True)),
        wet_enough_pct=_number(env, "WET_ENOUGH_PCT", d.wet_enough_pct, 1, 100),
        check_every_min=_number(env, "AUTO_WATER_EVERY_MIN", d.check_every_min, 1, 1440),
    )


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float,
            *, whole: bool = False) -> float:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not low <= value <= high or (whole and value != int(value)):  # also rejects nan
        kind = "a whole number" if whole else "a number"
        raise SettingsError(f"{name} must be {kind} from {low:g} to {high:g}, not {raw!r}.")
    return value


# ---------------------------------------------------------------- the files


def read_commands() -> list[dict[str, Any]]:
    return list(store._read(COMMANDS_FILE))


def read_results() -> list[dict[str, Any]]:
    return list(store._read(RESULTS_FILE))


def append_command(command: dict[str, Any]) -> None:
    store._append(COMMANDS_FILE, command)


def append_result(result: dict[str, Any]) -> None:
    result.setdefault("taken_at", store.now_iso())
    store._append(RESULTS_FILE, result)


def new_command(seconds: int, reason: str, requested_by: str, now: datetime) -> dict[str, Any]:
    return {
        "id": f"{now:%Y%m%dT%H%M%S}-{secrets.token_hex(2)}",
        "taken_at": now.isoformat(timespec="seconds"),
        "action": "water",
        "seconds": int(seconds),
        "reason": reason,
        "requested_by": requested_by,
    }


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def statuses(commands: Iterable[Mapping[str, Any]], results: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each command with `status`: its latest result's status, or "pending"."""
    latest: dict[str, str] = {}
    for result in results:
        if isinstance(result.get("command_id"), str) and isinstance(result.get("status"), str):
            latest[result["command_id"]] = result["status"]
    out = []
    for command in commands:
        if command.get("action") == "water" and isinstance(command.get("id"), str):
            out.append({**command, "status": latest.get(command["id"], PENDING)})
    return out


def _counted(history: Iterable[Mapping[str, Any]], now: datetime) -> list[datetime]:
    """Times of waterings that ran or may have run, oldest first."""
    times = []
    for item in history:
        t = parse_time(item.get("taken_at"))
        if t is None or item.get("status") not in COUNTED:
            continue
        if item.get("status") == PENDING and now - t > COMMAND_TTL + timedelta(seconds=ABSOLUTE_MAX_SECONDS):
            continue  # the bridge never picked it up, and never will: it is too old to run
        times.append(t)
    return sorted(times)


# ---------------------------------------------------------------- the rules


@dataclass(frozen=True)
class Decision:
    allowed: bool
    seconds: int
    reason: str  # plain text, one or two sentences
    needs_override: bool = False  # soil is wet or unknown: only a confirmed manual request may go on
    soil_pct: float | None = None
    soil_simulated: bool = False


def check(settings: WaterSettings, *, now: datetime, soil: Mapping[str, Any] | None,
          history: Iterable[Mapping[str, Any]], seconds: int | None = None,
          manual: bool = False, override: bool = False) -> Decision:
    """May the pump run now? `soil` is the latest sensors.jsonl record (or None),
    `history` the commands with their status (see statuses()). `override` is a
    confirmed manual "water anyway"; it only lifts the soil rule."""
    run = max(1, min(int(seconds or settings.seconds), settings.max_seconds))
    soil_pct, simulated = _soil(soil, now)

    def no(reason: str, needs_override: bool = False) -> Decision:
        return Decision(False, run, reason, needs_override, soil_pct, simulated)

    if not manual and not settings.auto:
        return no("Automatic watering is off (AUTO_WATER=0).")

    times = _counted(history, now)
    today = [t for t in times if t.astimezone(now.tzinfo).date() == now.date()]
    if len(today) >= settings.max_per_day:
        return no(f"Already watered {len(today)} times today, the daily limit "
                  f"(MAX_WATERINGS_PER_DAY={settings.max_per_day}).")
    if times:
        since = now - times[-1]
        cooldown = timedelta(minutes=settings.cooldown_min)
        if since < cooldown:
            wait = math.ceil((cooldown - since).total_seconds() / 60)
            ago = max(0, int(since.total_seconds() // 60))
            return no(f"The last watering was {ago} min ago. Wait {wait} min more "
                      f"(WATER_COOLDOWN_MIN={settings.cooldown_min:g}).")

    soil_issue = None
    if soil_pct is None:
        soil_issue = "There is no fresh soil moisture reading, so I can't tell if the soil is dry."
    elif soil_pct > settings.wet_enough_pct:
        soil_issue = (f"The soil is at {_pct(soil_pct, simulated)}, above the wet-enough "
                      f"level of {settings.wet_enough_pct:g}% (WET_ENOUGH_PCT).")
    if soil_issue and not (manual and override):
        return no(soil_issue, needs_override=manual)

    if soil_issue:
        reason = f"Watering for {run} s, as you confirmed. {soil_issue}"
    else:
        reason = f"Watering for {run} s: soil at {_pct(soil_pct, simulated)}."
    return Decision(True, run, reason, False, soil_pct, simulated)


def _soil(record: Mapping[str, Any] | None, now: datetime) -> tuple[float | None, bool]:
    if not record:
        return None, False
    value = record.get("soil_moisture_pct")
    t = parse_time(record.get("taken_at"))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None, False
    if t is None or now - t > SOIL_FRESH or t - now > timedelta(minutes=5):
        return None, False
    return float(value), record.get("simulated") is True


def _pct(value: float | None, simulated: bool) -> str:
    return f"{value:.0f}%" + (" (simulated)" if simulated else "")


def request(settings: WaterSettings, *, now: datetime, requested_by: str, reason: str,
            seconds: int | None = None, manual: bool = False, override: bool = False,
            soil: Mapping[str, Any] | None = None) -> tuple[Decision, dict[str, Any] | None]:
    """Check the rules against the files and, if allowed, queue the command.

    One lock covers the check and the write, so two taps at once queue one watering.
    Reads the latest soil reading from the store unless `soil` is given. Blocking.
    """
    with _lock:
        if soil is None:
            soil = store.latest_sensors(max_age=None)
        history = statuses(read_commands(), read_results())
        decision = check(settings, now=now, soil=soil, history=history, seconds=seconds,
                         manual=manual, override=override)
        if not decision.allowed:
            return decision, None
        command = new_command(decision.seconds, reason or decision.reason, requested_by, now)
        append_command(command)
        return decision, command


# ---------------------------------------------------------------- bridge side

ACK_RE = re.compile(r"^#\s*WATER_DONE\b\s*(\d+)?", re.I)
ERR_RE = re.compile(r"^#\s*WATER_ERR\b\s*(.*)$", re.I)
INFO_RE = re.compile(r"^#\s*WATER_\w+", re.I)


class WaterQueue:
    """The bridge's half: picks up new commands and records what happened to each.

    Call `poll(ser)` often while the board is connected, `poll_unavailable(why)`
    while it is not, and `on_line(line)` for every line the board sends. The
    `simulate` command (no board at all) calls `poll_simulated()` instead, which
    completes each command at once and marks the result "simulated": true.
    """

    def __init__(self, max_seconds: int = WaterSettings.max_seconds, *,
                 read: Callable[[], list[dict[str, Any]]] = read_commands,
                 read_done: Callable[[], list[dict[str, Any]]] = read_results,
                 write: Callable[[dict[str, Any]], None] = append_result,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 monotonic: Callable[[], float] = time.monotonic,
                 log: Any = None,
                 on_water: Callable[[int], None] | None = None):
        self.max_seconds = max(1, min(int(max_seconds), ABSOLUTE_MAX_SECONDS))
        self.read, self.write, self.now, self.monotonic = read, write, now, monotonic
        self.on_water = on_water
        self.log = log
        self.handled: set[str] = {r["command_id"] for r in read_done() if isinstance(r.get("command_id"), str)}
        self.awaiting: list[tuple[str, int, float]] = []  # (command id, seconds, ack deadline)

    def _result(self, command_id: str, status: str, seconds: int | None, detail: str, **extra: Any) -> None:
        record = {"command_id": command_id, "taken_at": self.now().astimezone().isoformat(timespec="seconds"),
                  "status": status, "seconds": seconds, "detail": detail, **extra}
        self.write(record)
        if self.log:
            self.log.info("watering %s: %s (%s)", command_id, status, detail)

    def _new(self) -> list[tuple[str, int]]:
        """New valid commands as (id, seconds). Invalid or stale ones get their result here."""
        fresh = []
        now = self.now()
        try:
            commands = self.read()
        except Exception as e:  # never let the queue file stop the sensor readings
            if self.log:
                self.log.warning("cannot read %s: %s", COMMANDS_FILE, e)
            return []
        for command in commands:
            command_id = command.get("id")
            if not isinstance(command_id, str) or command_id in self.handled:
                continue
            self.handled.add(command_id)
            seconds = command.get("seconds")
            taken = parse_time(command.get("taken_at"))
            if command.get("action") != "water":
                self._result(command_id, FAILED, None, f"unknown action {command.get('action')!r}")
            elif type(seconds) is not int or not 1 <= seconds <= self.max_seconds:
                self._result(command_id, FAILED, None,
                             f"seconds must be a whole number from 1 to {self.max_seconds}, not {seconds!r}")
            elif taken is None or now - taken > COMMAND_TTL:
                self._result(command_id, EXPIRED, seconds,
                             "too old to run safely; the bridge was not running when it was queued")
            elif taken - now > timedelta(minutes=5):
                self._result(command_id, FAILED, seconds, "its time is in the future; check the laptop clock")
            else:
                fresh.append((command_id, seconds))
        return fresh

    def _check_acks(self) -> None:
        now = self.monotonic()
        for item in [a for a in self.awaiting if now > a[2]]:
            self.awaiting.remove(item)
            self._result(item[0], NO_ACK, item[1],
                         "sent, but the board did not confirm; is the watering code flashed?")

    def poll(self, ser: Any) -> None:
        self._check_acks()
        for command_id, seconds in self._new():
            try:
                ser.write(f"WATER={seconds}\n".encode("ascii"))
                flush = getattr(ser, "flush", None)
                if flush:
                    flush()
            except Exception as e:  # a vanished port raises OSError or serial.SerialException
                self._result(command_id, FAILED, seconds, f"could not write to the board: {e}")
                continue
            self.awaiting.append((command_id, seconds, self.monotonic() + seconds + ACK_GRACE_S))
            self._result(command_id, SENT, seconds, f"sent WATER={seconds} to the board")

    def poll_unavailable(self, why: str) -> None:
        self._check_acks()
        for command_id, seconds in self._new():
            self._result(command_id, FAILED, seconds, why)

    def poll_simulated(self) -> None:
        for command_id, seconds in self._new():
            if self.on_water:
                self.on_water(seconds)
            self._result(command_id, DONE, seconds, "simulated: no board connected, nothing ran", simulated=True)

    def on_line(self, line: str) -> bool:
        """Handle the board's watering replies. True if the line was one of them."""
        text = line.strip()
        if match := ACK_RE.match(text):
            if self.awaiting:
                command_id, seconds, _ = self.awaiting.pop(0)
                self._result(command_id, DONE, seconds, "the board confirmed", board_reply=text)
            elif self.log:
                self.log.info("board: %s (no watering was waiting for it)", text)
            return True
        if match := ERR_RE.match(text):
            if self.awaiting:
                command_id, seconds, _ = self.awaiting.pop(0)
                self._result(command_id, FAILED, seconds, f"the board refused: {match[1] or 'no reason'}",
                             board_reply=text)
            return True
        if INFO_RE.match(text):
            if self.log:
                self.log.info("board: %s", text)
            return True
        return False
