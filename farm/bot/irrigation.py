"""Watering advice for the orange trees: a rule of thumb, not an agronomic plan.

`advise` is pure. It takes the sensor history (records as in farm/CONTRACT.md),
an optional weather forecast, today's date and the settings, and returns a
cadence, the next watering day, a one-line reason and the inputs it used.

How it decides (all thresholds are settings, see README "Irrigation advice"):
1. Soil moisture leads. If the latest fresh soil reading is below
   WATER_BELOW_PCT, the advice is "water today".
2. Otherwise the cadence comes from this week's water demand:
       demand = Kc x ET0 (mm over 7 days) - rain (mm over 7 days)
   with Kc the citrus crop coefficient and ET0 the reference evapotranspiration,
   from the Open-Meteo forecast if FARM_LAT/FARM_LON are set, else a Hargreaves
   estimate from the sensor temperatures. The demand maps to a cadence:
       < HOLD_OFF_BELOW_MM               hold off
       < WEEKLY_FROM_MM                  every 2 weeks
       < TWICE_WEEKLY_FROM_MM            weekly
       otherwise                         twice a week
3. The next watering day comes from the soil drying trend when there is one,
   else from the cadence counted from today.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

WATER_TODAY = "water today"
TWICE_WEEKLY = "twice a week"
WEEKLY = "weekly"
EVERY_2_WEEKS = "every 2 weeks"
HOLD_OFF = "hold off"
NOT_TODAY = "not today"  # soil is fine, but there is nothing to estimate demand from
UNKNOWN = "not enough data"

INTERVAL_DAYS = {TWICE_WEEKLY: 3, WEEKLY: 7, EVERY_2_WEEKS: 14}

SOIL_MAX_AGE = timedelta(hours=6)
HISTORY_DAYS = 7
ASSUMED_LATITUDE = 34.0  # Los Angeles, the default TIMEZONE; used only if FARM_LAT is not set
ASSUMED_DAILY_RANGE_C = 10.0  # used only if no day has readings spread over 12 hours
MIN_DAY_SPAN = timedelta(hours=12)
DRYING_MIN_PCT_PER_DAY = 0.5


@dataclass(frozen=True)
class IrrigationConfig:
    water_below_pct: float = 35.0
    kc: float = 0.65
    hold_off_below_mm: float = 5.0
    weekly_from_mm: float = 12.0
    twice_weekly_from_mm: float = 25.0
    latitude: float | None = None
    longitude: float | None = None

    @property
    def forecast_expected(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True)
class WeatherDay:
    day: date
    et0_mm: float | None
    rain_mm: float | None


@dataclass(frozen=True)
class Weather:
    days: tuple[WeatherDay, ...]
    source: str = "Open-Meteo forecast"


@dataclass(frozen=True)
class Advice:
    cadence: str
    next_due: date | None
    reason: str  # plain text, one line
    inputs_used: tuple[str, ...] = ()
    simulated: bool = False
    demand_mm: float | None = None


def advise(sensor_history: Iterable[Mapping[str, Any]], weather: Weather | None, today: date,
           config: IrrigationConfig, *, now: datetime | None = None) -> Advice:
    """Watering advice. `now` (timezone-aware) judges soil freshness; without it a
    soil reading counts as fresh if it was taken today."""
    readings = [r for r in (_reading(r) for r in sensor_history) if r is not None]
    readings.sort(key=lambda r: r["t"])
    cutoff = today - timedelta(days=HISTORY_DAYS)
    recent = [r for r in readings if r["t"].date() > cutoff]
    inputs: list[str] = []
    simulated = False

    soil = _latest_soil(recent, today, now)
    if soil is not None:
        simulated |= soil["simulated"]
        inputs.append(f"Soil moisture {_fmt(soil['soil'])}% at {_clock(soil['t'])}"
                      + (" (simulated)" if soil["simulated"] else ""))

    rain_soon = _rain_soon(weather, today)
    if soil is not None and soil["soil"] < config.water_below_pct:
        reason = f"Soil moisture is {_fmt(soil['soil'])}%, below {_fmt(config.water_below_pct)}%."
        if rain_soon:
            reason += f" {_fmt(rain_soon)} mm of rain is forecast by tomorrow, so a light watering may do."
        inputs.append(f"Threshold: water below {_fmt(config.water_below_pct)}% (WATER_BELOW_PCT)")
        return Advice(WATER_TODAY, today, reason, tuple(inputs), simulated)

    demand = _demand(recent, weather, today, config, inputs)
    if demand is None:
        if soil is not None:
            reason = (f"Soil moisture is {_fmt(soil['soil'])}%, so no need to water today. "
                      "Set FARM_LAT and FARM_LON for a weekly plan.")
            return Advice(NOT_TODAY, None, reason, tuple(inputs), simulated)
        reason = ("Not enough data for watering advice. Set FARM_LAT and FARM_LON in farm/bot/.env "
                  "for a forecast, or connect the sensor board.")
        return Advice(UNKNOWN, None, reason, tuple(inputs), False)

    net, need, rain, sim = demand
    simulated |= sim
    cadence = _cadence(net, config)
    rain_part = f" and {_fmt(rain)} mm of rain is forecast" if rain else ""
    if cadence == HOLD_OFF and rain:
        reason = f"The trees need about {_fmt(need)} mm this week{rain_part}, which covers most of it."
    elif cadence == HOLD_OFF:
        reason = f"The trees need only about {_fmt(need)} mm this week."
    else:
        reason = f"The trees need about {_fmt(need)} mm this week{rain_part}."
    inputs.append(f"Kc {config.kc:g} for citrus; demand {_fmt(net)} mm this week; "
                  f"thresholds {_fmt(config.hold_off_below_mm)} / {_fmt(config.weekly_from_mm)} / "
                  f"{_fmt(config.twice_weekly_from_mm)} mm")

    next_due, from_trend = _next_due(cadence, recent, soil, today, config)
    if from_trend:
        inputs.append("Next day from the soil drying trend over the last 3 days")
    elif next_due is not None:
        inputs.append(f"Next day counted from today ({INTERVAL_DAYS[cadence]} days): no soil drying trend yet, "
                      "so count from your last watering if you know it")
    return Advice(cadence, next_due, reason, tuple(inputs), simulated, round(net, 1))


# --- demand ------------------------------------------------------------------


def _demand(recent: list[dict], weather: Weather | None, today: date, config: IrrigationConfig,
            inputs: list[str]) -> tuple[float, float, float, bool] | None:
    """(net demand, crop need, rain) in mm over 7 days, and whether simulated data was used."""
    forecast = _forecast_week(weather, today)
    if forecast is not None:
        et0, rain, n = forecast
        source = weather.source if weather else "forecast"
        inputs.append(f"{source}, {n} days: ET0 {_fmt(et0)} mm, rain {_fmt(rain)} mm (scaled to 7 days)"
                      if n < 7 else f"{source}, next 7 days: ET0 {_fmt(et0)} mm, rain {_fmt(rain)} mm")
        need = config.kc * et0
        return max(need - rain, 0.0), need, rain, False

    if config.forecast_expected:
        inputs.append("Open-Meteo forecast unavailable, so ET0 is estimated from the sensors")
    estimate = _hargreaves_week(recent, today, config, inputs)
    if estimate is None:
        return None
    et0, sim = estimate
    inputs.append("No rain data: rain assumed to be zero")
    need = config.kc * et0
    return need, need, 0.0, sim


def _forecast_week(weather: Weather | None, today: date) -> tuple[float, float, int] | None:
    if weather is None:
        return None
    days = [d for d in weather.days if today <= d.day < today + timedelta(days=7) and d.et0_mm is not None]
    if not days:
        return None
    scale = 7 / len(days)
    et0 = sum(max(d.et0_mm, 0.0) for d in days) * scale
    rain = sum(max(d.rain_mm or 0.0, 0.0) for d in days) * scale
    return et0, rain, len(days)


def _hargreaves_week(recent: list[dict], today: date, config: IrrigationConfig,
                     inputs: list[str]) -> tuple[float, bool] | None:
    temps = [r for r in recent if r["temp"] is not None]
    if not temps:
        return None
    simulated = any(r["simulated"] for r in temps)
    lat = config.latitude
    if lat is None:
        lat = ASSUMED_LATITUDE
        lat_note = f"assumed latitude {lat:.2f} (set FARM_LAT)"
    else:
        lat_note = f"latitude {lat:.2f}"

    by_day: dict[date, list[dict]] = {}
    for r in temps:
        by_day.setdefault(r["t"].date(), []).append(r)
    full_days = [(d, rs) for d, rs in sorted(by_day.items())
                 if len(rs) >= 3 and rs[-1]["t"] - rs[0]["t"] >= MIN_DAY_SPAN]
    if full_days:
        daily = []
        for d, rs in full_days:
            lo, hi = min(r["temp"] for r in rs), max(r["temp"] for r in rs)
            daily.append(hargreaves_et0(lo, hi, lat, d))
        et0_day = sum(daily) / len(daily)
        lows = [min(r["temp"] for r in rs) for _, rs in full_days]
        highs = [max(r["temp"] for r in rs) for _, rs in full_days]
        how = (f"Hargreaves estimate from sensor temperatures over {len(full_days)} day{"s" if len(full_days) > 1 else ""} "
               f"(low {_fmt(sum(lows) / len(lows))} °C, high {_fmt(sum(highs) / len(highs))} °C), {lat_note}")
    else:
        mean = sum(r["temp"] for r in temps) / len(temps)
        half = ASSUMED_DAILY_RANGE_C / 2
        et0_day = hargreaves_et0(mean - half, mean + half, lat, today)
        how = (f"Hargreaves estimate from the mean sensor temperature {_fmt(mean)} °C with an assumed "
               f"{_fmt(ASSUMED_DAILY_RANGE_C)} °C daily range (no full day of readings yet), {lat_note}")

    factor, notes = _air_factor(recent)
    if notes:
        how += "; " + notes
    inputs.append(how + (" (simulated)" if simulated else ""))
    return et0_day * 7 * factor, simulated


def _air_factor(recent: list[dict]) -> tuple[float, str]:
    """Hargreaves ignores humidity and wind; nudge it for dry or windy air."""
    factor, notes = 1.0, []
    hums = [r["hum"] for r in recent if r["hum"] is not None]
    winds = [r["wind"] for r in recent if r["wind"] is not None]
    if hums:
        hum = sum(hums) / len(hums)
        if hum < 40:
            factor *= 1.1
            notes.append(f"dry air ({_fmt(hum)}% humidity) +10%")
        elif hum > 70:
            factor *= 0.9
            notes.append(f"humid air ({_fmt(hum)}% humidity) -10%")
    if winds:
        wind = sum(winds) / len(winds)
        if wind >= 4:
            factor *= 1.1
            notes.append(f"windy ({_fmt(wind)} m/s) +10%")
    return factor, ", ".join(notes)


def hargreaves_et0(t_min: float, t_max: float, latitude: float, day: date) -> float:
    """Daily reference evapotranspiration in mm (Hargreaves-Samani, FAO-56 eq. 52)."""
    if t_max < t_min:
        t_min, t_max = t_max, t_min
    ra = extraterrestrial_radiation(latitude, day)  # MJ m-2 day-1
    t_mean = (t_min + t_max) / 2
    return max(0.0, 0.0023 * (t_mean + 17.8) * math.sqrt(t_max - t_min) * 0.408 * ra)


def extraterrestrial_radiation(latitude: float, day: date) -> float:
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21)."""
    j = day.timetuple().tm_yday
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    delta = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))


def _cadence(net: float, config: IrrigationConfig) -> str:
    if net < config.hold_off_below_mm:
        return HOLD_OFF
    if net < config.weekly_from_mm:
        return EVERY_2_WEEKS
    if net < config.twice_weekly_from_mm:
        return WEEKLY
    return TWICE_WEEKLY


def _next_due(cadence: str, recent: list[dict], soil: dict | None, today: date,
              config: IrrigationConfig) -> tuple[date | None, bool]:
    """(next watering day, whether it came from the soil trend)."""
    interval = INTERVAL_DAYS.get(cadence)
    trend = _days_until_dry(recent, soil, config) if soil is not None else None
    if trend is not None and trend <= (interval if interval is not None else 7):
        return today + timedelta(days=max(1, trend)), True
    return (today + timedelta(days=interval) if interval is not None else None), False


def _days_until_dry(recent: list[dict], soil: dict, config: IrrigationConfig) -> int | None:
    """Days until soil reaches the threshold at the recent drying rate (least squares)."""
    since = soil["t"] - timedelta(days=3)
    points = [(r["t"], r["soil"]) for r in recent if r["soil"] is not None and since <= r["t"] <= soil["t"]]
    if len(points) < 3 or points[-1][0] - points[0][0] < timedelta(hours=12):
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [v for _, v in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var  # pct per day
    if slope > -DRYING_MIN_PCT_PER_DAY:
        return None
    return math.ceil((soil["soil"] - config.water_below_pct) / -slope)


def _rain_soon(weather: Weather | None, today: date) -> float:
    if weather is None:
        return 0.0
    return sum(max(d.rain_mm or 0.0, 0.0) for d in weather.days if today <= d.day <= today + timedelta(days=1))


# --- reading records -----------------------------------------------------------


def _reading(record: Mapping[str, Any]) -> dict | None:
    if not isinstance(record, Mapping) or not isinstance(record.get("taken_at"), str):
        return None
    try:
        t = datetime.fromisoformat(record["taken_at"])
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()  # contract says times carry an offset; assume laptop local time if not
    return {"t": t, "simulated": record.get("simulated") is True,
            "soil": _number(record.get("soil_moisture_pct")), "temp": _number(record.get("temperature_c")),
            "hum": _number(record.get("humidity_pct")), "wind": _number(record.get("wind_ms"))}


def _latest_soil(recent: list[dict], today: date, now: datetime | None) -> dict | None:
    with_soil = [r for r in recent if r["soil"] is not None]
    if not with_soil:
        return None
    latest = with_soil[-1]
    if now is not None:
        return latest if now - latest["t"] <= SOIL_MAX_AGE else None
    return latest if latest["t"].date() == today else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


# --- wording -------------------------------------------------------------------


def headline(advice: Advice, today: date) -> str:
    """'Water twice a week, next on Tuesday, Nov 24.' in plain text."""
    if advice.cadence == WATER_TODAY:
        text = "Water today."
    elif advice.cadence == HOLD_OFF:
        text = "Hold off on watering."
    elif advice.cadence == NOT_TODAY:
        text = "No need to water today."
    elif advice.cadence == UNKNOWN:
        return "No watering advice yet."
    else:
        text = f"Water {advice.cadence}"
        text += f", next {_day(advice.next_due, today)}." if advice.next_due else "."
    return text


def advice_line(advice: Advice, today: date) -> str:
    """One line for the daily message, Telegram HTML."""
    label = "Watering (simulated sensors): " if advice.simulated else ""
    if advice.cadence == UNKNOWN:
        return html.escape(advice.reason, quote=False)
    return html.escape(f"{label}{headline(advice, today)} {advice.reason}", quote=False)


def water_message(advice: Advice, today: date) -> str:
    """The /water reply: advice, the inputs used, and what kind of advice it is. Telegram HTML."""
    title = headline(advice, today)
    lines = [f"<b>{html.escape(title, quote=False)}</b>", html.escape(advice.reason, quote=False)]
    if advice.simulated:
        lines.append("Some sensor data is simulated, so this advice is for the demo only.")
    if advice.inputs_used:
        lines += ["", "Based on:"] + [f"- {html.escape(i, quote=False)}" for i in advice.inputs_used]
    if advice.cadence != UNKNOWN:
        lines += ["", "<i>A rule of thumb with adjustable thresholds, not a measured plan. "
                  "Check the soil by hand before a big change.</i>"]
    return "\n".join(lines)


def _day(d: date, today: date) -> str:
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return f"on {d:%A}, {d:%b} {d.day}"


def _clock(t: datetime) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 or abs(value) >= 10 else f"{value:.1f}"
