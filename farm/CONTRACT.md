# CutieFarm laptop side: how the parts fit

Three programs run on the laptop. They never call each other. They share files in one data folder (`farm/data/`, or `$CUTIEFARM_DATA`), read and written only through `farm/common/store.py`.

```
webcam ──► vision runner ──► scans.jsonl ──┐
                                            ├──► Telegram bot ──► grower (9:00 daily, /status, ready-to-pick alerts)
Arduino ─► sensor bridge ──► sensors.jsonl ┘
```

| Folder | Owner | Writes | Reads |
|---|---|---|---|
| vision program (teammate, optional, via VISION_COMMAND) | teammate | `scans.jsonl`, `scans/*.jpg` | — |
| `farm/sensors/` | sensor bridge (+ reference Arduino sketch) | `sensors.jsonl` | — |
| `farm/bot/` | Telegram bot | its own `bot_state.json` | both files |
| `farm/common/` | shared, change only by agreement | — | — |
| `ml/image-classification/` | **the teammate's CNN. Do not edit.** | | |
| `web/` | landing page and in-browser scanner | | |

## Labels

`unripe`, `ripening` and `ripe` (ready to pick) are the same labels used by the web scanner. A scan with no fruit has an empty `fruits` list. Confidence is `high`, `medium` or `low`. Readers ignore old labels outside this list and any unused fields.

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
     "scores": {"unripe": 0.02, "ripening": 0.10, "ripe": 0.88},
     "bbox": [412, 220, 96, 98]},
    {"id": 2, "label": "ripening", "confidence": "medium",
     "scores": {"unripe": 0.25, "ripening": 0.52, "ripe": 0.23},
     "bbox": [130, 300, 90, 92]}
  ],
  "summary": {"unripe": 0, "ripening": 1, "ripe": 1}
}
```

- `source`: `webcam` or `file`. `model`: which classifier produced the labels (`color-heuristic-v1` until the CNN is plugged in).
- `id` identifies the scan and is unique across scans.
- `image` is the optional whole-scan image path, relative to the data folder. It can be `null` when there is no image.
- `bbox` is `[x, y, w, h]` in pixels of the saved image.
- `summary` is filled by `store.append_scan`.

## `sensors.jsonl`

```json
{"taken_at": "2026-11-21T08:59:30-08:00", "soil_moisture_pct": 41.0, "temperature_c": 22.4,
 "humidity_pct": 55.0, "wind_ms": 3.2, "raw": "SOIL=612;T=22.4;H=55;W=3.2"}
```

Any sensor that isn't connected is `null`. Never invent a value. A reading produced by a simulator (for demos without the board) carries `"simulated": true`, and anything that shows it to a person must say so.

## Times

ISO 8601 with the local UTC offset (`store.now_iso()`). The laptop is in Pacific time.
