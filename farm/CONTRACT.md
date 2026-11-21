# CutieFarm laptop side: how the parts fit

Three programs run on the laptop. They never call each other. They share files in one data folder (`farm/data/`, or `$CUTIEFARM_DATA`), read and written only through `farm/common/store.py`.

```
webcam ──► vision runner ──► scans.jsonl ──┐
                                            ├──► Telegram bot ──► grower (9:00 daily, /status)
Arduino ─► sensor bridge ──► sensors.jsonl ┘
```

| Folder | Owner | Writes | Reads |
|---|---|---|---|
| vision program (teammate, optional, via VISION_COMMAND) | teammate | `scans.jsonl`, `scans/*.jpg` | — |
| `farm/sensors/` | sensor bridge (+ reference Arduino sketch) | `sensors.jsonl`, `irrigation_results.jsonl` | `irrigation.jsonl` |
| `farm/bot/` | Telegram bot | its own `bot_state.json`, `irrigation.jsonl` | `scans.jsonl`, `sensors.jsonl`, `irrigation_results.jsonl` |
| `farm/irrigation_control.py` | shared: the watering queue files and every safety rule | — | — |
| `farm/common/` | shared, change only by agreement | — | — |
| `ml/image-classification/` | **the teammate's CNN. Do not edit.** | | |
| `web/` | landing page and in-browser scanner | | |

## Labels

`unripe`, `ripening`, `ripe`, `mold`. They are the same as the web scanner's labels; `none` is never stored, a scan with no fruit simply has an empty `fruits` list. Confidence is `high`, `medium` or `low`, never a fake-precise percentage.

## `scans.jsonl` (one JSON object per line)

```json
{
  "id": "20261121T090012-3f9a",
  "taken_at": "2026-11-21T09:00:12-08:00",
  "source": "webcam",
  "model": "color-heuristic-v1",
  "image": "scans/20261121T090012-3f9a.jpg",
  "fruits": [
    {"id": 1, "label": "ripe", "confidence": "high",
     "scores": {"unripe": 0.02, "ripening": 0.10, "ripe": 0.85, "mold": 0.03},
     "bbox": [412, 220, 96, 98],
     "crop": null},
    {"id": 2, "label": "mold", "confidence": "medium", "scores": {"...": 0},
     "bbox": [130, 300, 90, 92],
     "crop": "scans/20261121T090012-3f9a-2.jpg"}
  ],
  "summary": {"unripe": 0, "ripening": 0, "ripe": 1, "mold": 1}
}
```

- `source`: `webcam` or `file`. `model`: which classifier produced the labels (`color-heuristic-v1` until the CNN is plugged in).
- `image` and `crop` are paths relative to the data folder. `crop` is saved at least for every `mold` fruit, so the bot can send its photo.
- `bbox` is `[x, y, w, h]` in pixels of the saved image.
- `summary` is filled by `store.append_scan`.

## `sensors.jsonl`

```json
{"taken_at": "2026-11-21T08:59:30-08:00", "soil_moisture_pct": 41.0, "temperature_c": 22.4,
 "humidity_pct": 55.0, "wind_ms": 3.2, "raw": "SOIL=612;T=22.4;H=55;W=3.2"}
```

Any sensor that isn't connected is `null`. Never invent a value. A reading produced by a simulator (for demos without the board) carries `"simulated": true`, and anything that shows it to a person must say so.

## Watering: `irrigation.jsonl` and `irrigation_results.jsonl`

The bot asks for watering by appending a command to `irrigation.jsonl`. The sensor bridge, the only program that holds the Arduino's serial port, picks each new command up within about a second. It sends `WATER=<seconds>` to the board and appends what happened to `irrigation_results.jsonl`. Both files are read and written only through `farm/irrigation_control.py`, which also holds the safety rules (see `farm/bot/README.md`, "Watering the grove").

```json
{"id": "20261121T141502-9c1e", "taken_at": "2026-11-21T14:15:02-08:00", "action": "water", "seconds": 8,
 "reason": "Soil moisture is 28%, below 35%.", "requested_by": "auto"}
```

- `action` is always `water`. `seconds` is a whole number from 1 to `MAX_WATER_SECONDS` (default 15, never above 30).
- `requested_by` is `auto` (automatic mode) or `chat:<telegram chat id>` (`/water_now`).
- The bot queues a command only after the safety checks pass. The bridge checks `seconds` again, and the board has its own cap.

```json
{"command_id": "20261121T141502-9c1e", "taken_at": "2026-11-21T14:15:03-08:00", "status": "sent", "seconds": 8,
 "detail": "sent WATER=8 to the board"}
{"command_id": "20261121T141502-9c1e", "taken_at": "2026-11-21T14:15:11-08:00", "status": "done", "seconds": 8,
 "detail": "the board confirmed", "board_reply": "#WATER_DONE 8"}
```

A command can have several results. The last one is its status:

| `status` | Meaning |
|---|---|
| (no result yet) | pending: the bridge hasn't picked it up |
| `sent` | `WATER=<n>` was written to the board; waiting for `#WATER_DONE` |
| `done` | the board printed `#WATER_DONE <n>`, or the simulator ran it (`"simulated": true`: no water ran) |
| `no_ack` | sent, but no `#WATER_DONE` came within `seconds` + 10 s. The pump may or may not have run. |
| `failed` | not run: no board connected, a write error, an invalid command, or the board refused it (`#WATER_ERR ...`) |
| `expired` | the command was over 2 minutes old when the bridge saw it (it was not running), so it was not run |

- `python -m farm.sensors simulate` (no board) completes every command at once with `"status": "done", "simulated": true`, and the simulated soil gets wetter. Anything that shows such a result to a person must say no water ran.
- The bridge never sends a command twice. On start, it skips commands that already have a result.
- Waterings with status pending, `sent`, `done` or `no_ack` count toward the cooldown and the daily cap. `failed` and `expired` ones don't.

Board side: one line `WATER=<seconds>` from the laptop, ending in a newline. The board answers `#WATER_START <n>`, then `#WATER_DONE <n>` when the pump stops, or `#WATER_ERR <why>` if it refuses. `WATER=0` stops the pump. See `farm/sensors/arduino/WATER_SNIPPET.md`.

## Times

ISO 8601 with the local UTC offset (`store.now_iso()`). The laptop is in Pacific time.
