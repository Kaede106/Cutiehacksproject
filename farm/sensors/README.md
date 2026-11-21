# CutieFarm sensor bridge

An Arduino reads the grove's sensors and prints one line per reading over USB serial. This bridge, running on the laptop, reads those lines and appends readings to `sensors.jsonl` through `farm/common/store.py`. The Telegram bot reads them from there. Record format: `farm/CONTRACT.md`.

```
soil probe ─► Arduino (A0) ─USB─► python -m farm.sensors listen ─► sensors.jsonl ─► bot
```

## Line protocol

The team's sketch (`sketch_nov21a`) prints human-readable lines, and the bridge accepts those as they are: `Temperature: 23.40 C`, `Humidity: 55.00 %`, `Raw: 612 | Moisture: 45%` (the raw value is used, and the bridge converts it with `--soil-dry`/`--soil-wet`). `Failed to read sensor` and `Ready` are skipped. Any other line must follow the protocol below.


One line per reading, ending in `\n` (`\r\n` is fine): `KEY=value` pairs separated by `;`, at 9600 baud.

```
# cutiefarm_sensors v1
SOIL=612;T=22.4;H=55;W=3.2
SOIL=598
```

| Key | Meaning | Units | Who calibrates | Record field |
|---|---|---|---|---|
| `SOIL` | soil moisture | **raw ADC counts** (0–1023 on an Uno) | the bridge, with `--soil-dry`/`--soil-wet` | `soil_moisture_pct` (0–100, clamped) |
| `T` | air temperature | °C | the board (DHT11/22 gives °C) | `temperature_c` |
| `H` | relative humidity | % RH | the board | `humidity_pct` |
| `W` | wind speed | m/s | the board (not implemented yet) | `wind_ms` |

Rules:

- Keys are case-insensitive. Spaces around keys and values are ignored, and so is a trailing `;`.
- **Missing keys become null.** A board without a DHT just sends `SOIL=612`. A sensor that failed this time can leave its key out or send `nan`; either way it is stored as null.
- **Unknown keys are ignored**, so the board can add keys (for example `VER=2`) before the bridge knows them.
- **Lines starting with `#` are comments**, used for boot messages. The bridge logs them.
- **Malformed lines are logged and skipped.** A line is malformed if a part has no `=`, a known key's value is not a finite number, a known key appears twice, the line has no known key at all, it is over 200 characters, or it contains non-printable bytes (usually a wrong baud rate).
- A value outside its plausible range (`SOIL` 0–65535, `T` −40–85, `H` 0–100, `W` 0–75) is logged and stored as null, while the rest of the line is kept.
- The first line after connecting is dropped, because it may be the end of a line sent before the port opened.

## What gets written

`listen` writes the first reading straight away, then at most once every `--every` seconds (default 60). Readings in between are averaged per sensor, ignoring nulls (raw `SOIL` is averaged before converting). `taken_at` is the time of the newest reading in the average, and `raw` is that reading's line.

```json
{"soil_moisture_pct":50.0,"temperature_c":null,"humidity_pct":null,"wind_ms":null,"raw":"SOIL=440","taken_at":"2026-11-21T10:02:11-08:00"}
```

- A sensor that is not connected is `null`. Nothing is ever filled in.
- If the board is unplugged, readings not yet written are dropped, and the bridge reconnects when it comes back.
- If nothing usable arrives, nothing is written. A reading older than an hour is treated as stale by `store.latest_sensors()`.
- `simulate` records also carry `"simulated": true`. Real records leave the key out.

Soil percentage: `pct = (dry − raw) / (dry − wet) × 100`, clamped to 0–100. This works for probes that read lower when wet (most do) and for probes that read higher. The defaults, `dry=600` and `wet=280`, are **rough**: they are typical of a capacitive v1.2 probe on a 5 V Uno. A resistive probe (two bare forks, e.g. YL-69/FC-28) reads about 1023 dry, so with the defaults it shows 0% until it is quite wet. Calibrate before trusting the number. The bridge warns at startup while it is still using the defaults.

## Setup (Windows, from the repo root)

```powershell
python -m venv farm\sensors\.venv
farm\sensors\.venv\Scripts\python -m pip install -r farm\sensors\requirements.txt
```

Or run it from the bot's venv: `farm/bot/requirements.txt` already includes pyserial. `python -m farm` starts the bridge together with the bot.

## Commands

All of these run from the repo root with `$py = "farm\sensors\.venv\Scripts\python"`:

```powershell
& $py -m farm.sensors ports                       # list serial ports; marks the one auto-detect would pick
& $py -m farm.sensors calibrate                   # guided dry + wet reading; prints --soil-dry/--soil-wet
& $py -m farm.sensors listen --soil-dry 587 --soil-wet 281             # auto-detect the port
& $py -m farm.sensors listen --port COM3 --baud 9600 --every 60s --soil-dry 587 --soil-wet 281
& $py -m farm.sensors simulate --every 10s        # demo without the board: "simulated": true
& $py -m farm.sensors simulate --every 2s --count 5
& $py -m pytest farm\sensors\tests -q
```

- `--every` takes `30`, `30s`, `2m` or `1h`. Add `-v` for debug logs, which include unknown keys and dropped lines.
- To avoid retyping the calibration, set `$env:CUTIEFARM_SOIL_DRY = 587` and `$env:CUTIEFARM_SOIL_WET = 281`. The flags override them.
- `CUTIEFARM_DATA` chooses the data folder, as for every CutieFarm program (default `farm/data/`).
- Auto-detect prefers Arduino USB IDs (2341, 2A03, SparkFun, Adafruit), then common clone USB-serial chips (CH340, FTDI, CP210x, PL2303). It skips Bluetooth serial ports. If nothing matches, `listen` keeps waiting until a board appears, and `--port COMx` overrides detection.
- Only one program can open a COM port at a time. Close the Arduino IDE Serial Monitor before running `listen` or `calibrate`. "Access is denied" means something else has the port.

## Wiring

Soil moisture probe (3 pins, labelled `VCC`, `GND`, `AOUT`/`A0`/`SIG`):

| Probe | Arduino Uno |
|---|---|
| VCC | 5V (or a digital pin, see below) |
| GND | GND |
| AOUT | A0 |

Some probes come with a small comparator board that has 4 pins. Use `A0`/`AO`, not `D0`/`DO`: the digital pin only gives wet or dry against the board's potentiometer.

**Powering the probe only while reading.** A resistive probe (two bare metal forks) passes DC current through wet soil. With constant power, electrolysis eats the forks in days to weeks, and the readings drift as they corrode. Many builds therefore feed the probe's VCC from a digital pin, switch it on for about 100 ms to read, then switch it off. Set `SOIL_POWER_PIN` in the sketch (e.g. `7`) and wire probe VCC to that pin instead of 5V. A probe draws a few mA, well within a pin's limit. Capacitive probes (one smooth black blade) don't corrode this way and can stay on 5V, though switching them is harmless. Recalibrate if you change how the probe is powered.

Optional DHT11/DHT22 (temperature + humidity): VCC to 5V, GND to GND, DATA to pin 2. Bare 4-pin sensors also need a 10 kΩ pull-up resistor from DATA to VCC; most breakout boards already have one. Then in the sketch, set `USE_DHT 1` and `DHT_TYPE`, and install "DHT sensor library" by Adafruit from the Library Manager. The DHT11 is coarser (±2 °C, ±5 % RH) than the DHT22.

Wind is not implemented: `readWind()` in the sketch is a TODO stub that sends nothing, so `wind_ms` stays null. Once you know the anemometer, return m/s from it and set `USE_WIND 1`.

## Arduino sketch

`arduino/cutiefarm_sensors/cutiefarm_sensors.ino`. Open it in the Arduino IDE, choose Board "Arduino Uno" and the port, and Upload. The settings at the top are the pins, `INTERVAL_MS` (2 s), `SOIL_SAMPLES`, `SOIL_POWER_PIN`, and the `USE_DHT`/`USE_WIND` switches. With both switches off, it needs no library beyond the core.

You can check the output in Serial Monitor at 9600 baud: you should see `# cutiefarm_sensors v1` and then `SOIL=...` every 2 s. Close the Serial Monitor before starting the bridge.

## Files

| File | What |
|---|---|
| `protocol.py` | line parser, soil calibration, record builder |
| `bridge.py` | port detection, line reading, averaging, the reconnecting `listen` loop |
| `calibrate.py` | interactive dry/wet calibration |
| `simulate.py` | simulated readings for demos |
| `__main__.py` | command line |
| `tests/` | pytest; no hardware needed (the serial port is faked) |
