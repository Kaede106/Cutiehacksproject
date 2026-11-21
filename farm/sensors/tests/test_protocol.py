import logging

import pytest

from farm.sensors.protocol import FIELDS, MalformedLine, SoilCalibration, parse_line, to_record


def test_full_line():
    assert parse_line("SOIL=612;T=22.4;H=55;W=3.2") == {"SOIL": 612.0, "T": 22.4, "H": 55.0, "W": 3.2}


def test_whitespace_case_crlf_and_trailing_semicolon():
    assert parse_line(" soil = 612 ; t=22.4;\r\n") == {"SOIL": 612.0, "T": 22.4, "H": None, "W": None}


def test_partial_line_missing_keys_are_none():
    assert parse_line("SOIL=612") == {"SOIL": 612.0, "T": None, "H": None, "W": None}


def test_explicit_nan_means_no_reading():
    assert parse_line("SOIL=612;T=nan;H=NaN") == {"SOIL": 612.0, "T": None, "H": None, "W": None}


def test_unknown_keys_ignored():
    assert parse_line("VER=2;SOIL=500;BATT=ok") == {"SOIL": 500.0, "T": None, "H": None, "W": None}


@pytest.mark.parametrize("line", ["", "   ", "\r\n", "# cutiefarm_sensors boot", "  #comment"])
def test_blank_and_comments(line):
    assert parse_line(line) is None


@pytest.mark.parametrize("line", [
    "hello world",            # no '='
    "SOIL612",                # no '='
    "SOIL=abc",               # not a number
    "SOIL=6x2;T=22",          # corrupted number
    "T=inf",                  # not finite
    "SOIL=1;SOIL=2",          # duplicate
    "=5",                     # empty key
    "SO IL=5",                # bad key
    "FOO=1;BAR=2",            # only unknown keys
    "SOIL=612\x00\xff\xfe",   # binary noise
    "��=�",    # undecodable bytes, typical of a wrong baud rate
    "SOIL=1;" * 100,          # far too long
])
def test_garbage_is_malformed(line):
    with pytest.raises(MalformedLine):
        parse_line(line)


def test_out_of_range_value_becomes_null(caplog):
    with caplog.at_level(logging.WARNING, logger="farm.sensors"):
        assert parse_line("SOIL=500;H=140") == {"SOIL": 500.0, "T": None, "H": None, "W": None}
    assert "H=140" in caplog.text


@pytest.mark.parametrize("raw,pct", [(600, 0.0), (280, 100.0), (440, 50.0), (360, 75.0)])
def test_soil_calibration(raw, pct):
    assert SoilCalibration(dry=600, wet=280).percent(raw) == pct


@pytest.mark.parametrize("raw,pct", [(1023, 0.0), (601, 0.0), (279, 100.0), (0, 100.0)])
def test_soil_calibration_clamps(raw, pct):
    assert SoilCalibration(dry=600, wet=280).percent(raw) == pct


def test_soil_calibration_for_probe_that_rises_when_wet():
    cal = SoilCalibration(dry=200, wet=800)
    assert cal.percent(200) == 0.0 and cal.percent(500) == 50.0 and cal.percent(900) == 100.0


def test_soil_calibration_none_and_invalid():
    assert SoilCalibration().percent(None) is None
    with pytest.raises(ValueError):
        SoilCalibration(dry=500, wet=500)


def test_soil_raw_for_round_trips():
    cal = SoilCalibration(dry=600, wet=280)
    assert cal.percent(cal.raw_for(41.0)) == pytest.approx(41.0, abs=0.3)


def test_record_has_contract_fields_and_nulls():
    raw = "SOIL=440;T=22.43"
    record = to_record(parse_line(raw), raw, SoilCalibration(600, 280))
    assert record == {"soil_moisture_pct": 50.0, "temperature_c": 22.4, "humidity_pct": None,
                      "wind_ms": None, "raw": raw}
    assert set(FIELDS) < set(record)
    assert "simulated" not in record
