# CutieFarm laptop side: how the parts fit

Three programs run on the laptop. They never call each other. They share files in one data folder (`farm/data/`, or `$CUTIEFARM_DATA`), read and written only through `farm/common/store.py`.

```
webcam ──► vision runner ──► scans.jsonl ──┐
                                            ├──► Telegram bot ──► grower (9:00 daily, /status)
Arduino ─► sensor bridge ──► sensors.jsonl ┘
```

| Folder | Owner | Writes | Reads |
|---|---|---|---|
| vision runner (teammate, ML/CV) | teammate | `scans.jsonl`, `scans/*.jpg` | — |
| sensor bridge (teammate, Arduino) | teammate | `sensors.jsonl` | — |
| `farm/bot/` | Telegram bot | its own `bot_state.json` | both files |
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

## Times

ISO 8601 with the local UTC offset (`store.now_iso()`). The laptop is in Pacific time.
