import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from farm.bot.compose import compose, to_plain
from farm.bot.config import ConfigError, parse_irrigation
from farm.bot.irrigation import (EVERY_2_WEEKS, HOLD_OFF, NOT_TODAY, TWICE_WEEKLY, UNKNOWN, WATER_TODAY, WEEKLY,
                                 Advice, IrrigationConfig, Weather, WeatherDay, advice_line, advise,
                                 extraterrestrial_radiation, hargreaves_et0, water_message)

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=LA)
TODAY = NOW.date()
CFG = IrrigationConfig()


def reading(ago, *, soil=None, temp=None, hum=None, wind=None, simulated=False):
    r = {"taken_at": (NOW - ago).isoformat(), "soil_moisture_pct": soil, "temperature_c": temp,
         "humidity_pct": hum, "wind_ms": wind}
    if simulated:
        r["simulated"] = True
    return r


def forecast(et0_per_day, rain=(0,) * 7, start=TODAY):
    return Weather(tuple(WeatherDay(start + timedelta(days=i), et0_per_day, r) for i, r in enumerate(rain)))


def full_days(n, t_low, t_high, **kw):
    """Readings every 3 hours over n days, low at night and high in the afternoon."""
    out = []
    for i in range(n * 8, -1, -1):
        ago = timedelta(hours=3 * i, minutes=5)
        hour = (NOW - ago).hour
        out.append(reading(ago, temp=t_high if 12 <= hour <= 17 else t_low, **kw))
    return out


# --- soil leads ---------------------------------------------------------------


def test_dry_soil_means_water_today_whatever_the_forecast():
    a = advise([reading(timedelta(minutes=10), soil=28)], forecast(1.0, rain=(0,) * 7), TODAY, CFG, now=NOW)
    assert a.cadence == WATER_TODAY and a.next_due == TODAY
    assert a.reason == "Soil moisture is 28%, below 35%."


def test_dry_soil_with_rain_coming_mentions_it():
    a = advise([reading(timedelta(minutes=10), soil=30)], forecast(1.0, rain=(4, 8, 0, 0, 0, 0, 0)), TODAY, CFG,
               now=NOW)
    assert a.cadence == WATER_TODAY and "12 mm of rain is forecast by tomorrow" in a.reason


def test_threshold_is_configurable():
    a = advise([reading(timedelta(minutes=10), soil=38)], None, TODAY, IrrigationConfig(water_below_pct=40), now=NOW)
    assert a.cadence == WATER_TODAY


def test_old_soil_reading_does_not_lead():
    a = advise([reading(timedelta(hours=7), soil=20)], None, TODAY, CFG, now=NOW)
    assert a.cadence == UNKNOWN


def test_without_now_soil_counts_only_if_from_today():
    yesterday = [reading(timedelta(hours=10), soil=20)]  # 11 PM yesterday
    assert advise(yesterday, None, TODAY, CFG).cadence == UNKNOWN
    assert advise([reading(timedelta(hours=1), soil=20)], None, TODAY, CFG).cadence == WATER_TODAY


# --- cadence from demand ------------------------------------------------------


@pytest.mark.parametrize("et0, rain, expected", [
    (6.0, 0, TWICE_WEEKLY),   # 0.65 * 42 = 27.3 mm
    (4.0, 0, WEEKLY),         # 18.2 mm
    (2.0, 0, EVERY_2_WEEKS),  # 9.1 mm
    (1.0, 0, HOLD_OFF),       # 4.6 mm
    (4.0, 2, HOLD_OFF),       # 18.2 - 14 = 4.2 mm
    (6.0, 1, WEEKLY),         # 27.3 - 7 = 20.3 mm
])
def test_cadence_from_forecast(et0, rain, expected):
    a = advise([], forecast(et0, rain=(rain,) * 7), TODAY, CFG)
    assert a.cadence == expected
    assert any("forecast" in i.lower() for i in a.inputs_used)


def test_hotter_drier_windier_weeks_water_more_often():
    order = [HOLD_OFF, EVERY_2_WEEKS, WEEKLY, TWICE_WEEKLY]
    ranks = [order.index(advise([], forecast(e), TODAY, CFG).cadence) for e in (0.5, 2, 4, 6, 8)]
    assert ranks == sorted(ranks) and ranks[0] < ranks[-1]


def test_rain_lowers_demand_but_not_below_zero():
    a = advise([], forecast(2.0, rain=(30,) * 7), TODAY, CFG)
    assert a.cadence == HOLD_OFF and a.demand_mm == 0
    assert "mm of rain is forecast, which covers most of it" in a.reason
    assert a.next_due is None


def test_kc_and_thresholds_are_configurable():
    assert advise([], forecast(4.0), TODAY, IrrigationConfig(kc=0.9)).cadence == TWICE_WEEKLY  # 25.2
    assert advise([], forecast(4.0), TODAY, IrrigationConfig(weekly_from_mm=20, twice_weekly_from_mm=30)
                  ).cadence == EVERY_2_WEEKS


def test_short_forecast_is_scaled_to_a_week():
    weather = Weather((WeatherDay(TODAY, 4.0, 0), WeatherDay(TODAY + timedelta(days=1), 4.0, 0)))
    a = advise([], weather, TODAY, CFG)
    assert a.cadence == WEEKLY and "2 days" in " ".join(a.inputs_used)


def test_past_forecast_days_are_ignored():
    old = forecast(6.0, start=TODAY - timedelta(days=10))
    assert advise([], old, TODAY, CFG).cadence == UNKNOWN


# --- next watering day --------------------------------------------------------


def test_next_day_from_soil_drying_trend():
    history = [reading(timedelta(days=2, minutes=10), soil=50), reading(timedelta(days=1, minutes=10), soil=46),
               reading(timedelta(minutes=10), soil=42)]  # -4 %/day, 7 points above 35
    a = advise(history, forecast(2.0), TODAY, CFG, now=NOW)
    assert a.cadence == EVERY_2_WEEKS and a.next_due == TODAY + timedelta(days=2)
    assert any("drying trend" in i for i in a.inputs_used)


def test_next_day_from_cadence_says_it_is_counted_from_today():
    a = advise([reading(timedelta(minutes=10), soil=50)], forecast(4.0), TODAY, CFG, now=NOW)
    assert a.cadence == WEEKLY and a.next_due == TODAY + timedelta(days=7)
    assert any("counted from today" in i for i in a.inputs_used)


# --- Hargreaves fallback -------------------------------------------------------


def test_extraterrestrial_radiation_matches_fao56_example():
    # FAO-56 example 8: 20 deg S on 3 September gives Ra = 32.2 MJ m-2 day-1.
    assert extraterrestrial_radiation(-20, date(2026, 9, 3)) == pytest.approx(32.2, abs=0.2)


def test_hargreaves_is_plausible_and_grows_with_heat_and_range():
    winter = hargreaves_et0(8, 18, 34, date(2026, 12, 21))
    summer = hargreaves_et0(18, 34, 34, date(2026, 6, 21))
    assert 1 < winter < 3 and 5 < summer < 8 and summer > winter
    assert hargreaves_et0(20, 20, 34, TODAY) == 0
    assert hargreaves_et0(25, 15, 34, TODAY) == hargreaves_et0(15, 25, 34, TODAY)


def test_sensor_estimate_used_without_forecast_and_says_how():
    a = advise(full_days(3, 12, 26), None, TODAY, CFG, now=NOW)
    assert a.cadence in (EVERY_2_WEEKS, WEEKLY)
    text = " ".join(a.inputs_used)
    assert "Hargreaves estimate from sensor temperatures over 3 days" in text
    assert "assumed latitude 34 (set FARM_LAT)" in text
    assert "No rain data: rain assumed to be zero" in text


def test_sensor_estimate_uses_farm_lat_when_set():
    a = advise(full_days(2, 12, 26), None, TODAY, IrrigationConfig(latitude=36.7))
    assert "latitude 36.7" in " ".join(a.inputs_used) and "assumed latitude" not in " ".join(a.inputs_used)


def test_single_reading_falls_back_to_an_assumed_daily_range():
    a = advise([reading(timedelta(minutes=5), temp=22)], None, TODAY, CFG, now=NOW)
    assert a.cadence != UNKNOWN
    assert "assumed 10 °C daily range" in " ".join(a.inputs_used)


def test_dry_windy_air_raises_the_sensor_estimate():
    calm = advise(full_days(2, 12, 26, hum=55, wind=1), None, TODAY, CFG).demand_mm
    harsh = advise(full_days(2, 12, 26, hum=25, wind=6), None, TODAY, CFG).demand_mm
    assert harsh == pytest.approx(calm * 1.21, rel=0.02)


def test_forecast_preferred_over_sensor_estimate():
    a = advise(full_days(2, 12, 26), forecast(6.0), TODAY, CFG)
    assert a.cadence == TWICE_WEEKLY and "Hargreaves" not in " ".join(a.inputs_used)


def test_expected_forecast_missing_is_reported():
    a = advise(full_days(2, 12, 26), None, TODAY, IrrigationConfig(latitude=34, longitude=-118))
    assert "Open-Meteo forecast unavailable" in " ".join(a.inputs_used)


# --- honesty ---------------------------------------------------------------------


def test_no_data_says_so_and_how_to_get_it():
    a = advise([], None, TODAY, CFG)
    assert a.cadence == UNKNOWN and a.next_due is None and not a.simulated
    assert "FARM_LAT and FARM_LON" in a.reason and "sensor board" in a.reason


def test_fresh_soil_without_demand_data_is_not_a_guess():
    a = advise([reading(timedelta(minutes=5), soil=50)], None, TODAY, CFG, now=NOW)
    assert a.cadence == NOT_TODAY and a.next_due is None


def test_simulated_data_is_flagged_everywhere():
    a = advise([reading(timedelta(minutes=5), soil=50, temp=22, simulated=True)], None, TODAY, CFG, now=NOW)
    assert a.simulated
    assert advice_line(a, TODAY).startswith("Watering (simulated sensors): ")
    assert "simulated" in water_message(a, TODAY)
    assert not advise([], forecast(4.0), TODAY, CFG).simulated


def test_bad_records_are_skipped():
    history = [{"taken_at": "nope", "soil_moisture_pct": 10}, {"soil_moisture_pct": 10}, "x",
               reading(timedelta(minutes=5), soil=True, temp="hot")]
    assert advise(history, None, TODAY, CFG, now=NOW).cadence == UNKNOWN


def test_water_message_lists_inputs_and_is_safe_html():
    a = advise([reading(timedelta(minutes=5), soil=50)], forecast(4.0), TODAY, CFG, now=NOW)
    text = water_message(a, TODAY)
    assert text.startswith("<b>Water weekly, next on Saturday, Nov 28.</b>")
    assert "Based on:" in text and "- Soil moisture 50% at 8:55 AM" in text
    assert "rule of thumb" in text and "!" not in text
    assert set(re.findall(r"</?([a-z]+)>", text)) <= {"b", "i"}


def test_advice_line_escapes_text():
    a = Advice(WEEKLY, TODAY + timedelta(days=1), "Need <5 mm & more.")
    assert advice_line(a, TODAY) == "Water weekly, next tomorrow. Need &lt;5 mm &amp; more."


def test_daily_message_puts_watering_after_the_oranges():
    scan = {"taken_at": NOW.isoformat(), "model": "cnn", "fruits": [],
            "summary": {"ripe": 2, "ripening": 0, "unripe": 0, "mold": 0}}
    a = advise([], forecast(4.0), TODAY, CFG)
    lines = to_plain(compose(scan, None, NOW, irrigation=a).text).split("\n\n")
    assert lines[0] == "2 ready to pick." and lines[2].startswith("Water weekly")
    assert "Water weekly" in to_plain(compose(None, None, NOW, irrigation=a).text)


# --- settings ----------------------------------------------------------------------


def test_irrigation_settings():
    c = parse_irrigation({"WATER_BELOW_PCT": "30", "CITRUS_KC": "0.7", "FARM_LAT": "34.05", "FARM_LON": "-118.24"})
    assert (c.water_below_pct, c.kc, c.latitude, c.longitude, c.forecast_expected) == (30, 0.7, 34.05, -118.24, True)
    assert parse_irrigation({}) == IrrigationConfig()
    assert parse_irrigation({"FARM_LAT": "34"}).forecast_expected is False


@pytest.mark.parametrize("env, name", [
    ({"FARM_LAT": "91"}, "FARM_LAT"), ({"FARM_LAT": "abc"}, "FARM_LAT"), ({"FARM_LAT": "nan"}, "FARM_LAT"),
    ({"FARM_LON": "-118"}, "FARM_LON"), ({"CITRUS_KC": "3"}, "CITRUS_KC"), ({"WATER_BELOW_PCT": "-1"}, "WATER_BELOW_PCT"),
    ({"WEEKLY_FROM_MM": "30"}, "TWICE_WEEKLY_FROM_MM"),
])
def test_bad_irrigation_settings(env, name):
    with pytest.raises(ConfigError, match=name):
        parse_irrigation(env)
