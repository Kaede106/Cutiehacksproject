# CutieFarm Telegram bot

Every morning at 9:00 (America/Los_Angeles) the bot tells the grower what to do with their oranges, based on the latest camera scan and sensor reading:

```
3 ready to pick, 5 ripening, 1 possible mold (photo attached): remove it today.

Remove the fruit with possible mold today, before the mold spreads.
Pick the 3 oranges that are ready.
Check the 5 ripening ones again in a few days.

Water weekly, next on Saturday, Nov 28. The trees need about 12 mm this week.

Sensors at 8:59 AM: soil moisture 41%, 22.4 °C (72 °F), humidity 55%, wind 3.2 m/s.

Scan: today at 9:00 AM.
Labels come from a colour check until the trained model is plugged in.
```

The photo of each fruit with possible mold (up to 3) follows the text. The bot only reads `scans.jsonl` and `sensors.jsonl` through `farm/common/store.py` (see `farm/CONTRACT.md`). It never talks to the camera or the board directly.

## Setup (Windows, Python 3.14)

From the repo root:

```powershell
python -m venv farm\bot\.venv
farm\bot\.venv\Scripts\python -m pip install -r farm\bot\requirements.txt
copy farm\bot\.env.example farm\bot\.env
```

The bot has its own venv. Do not share it with other programs.

### Create the bot with @BotFather

1. In Telegram, open a chat with **@BotFather** and send `/newbot`.
2. Pick a display name (for example "CutieFarm") and a username ending in `bot` (for example `cutiefarm_demo_bot`).
3. BotFather replies with a token like `123456789:AA...`. Put it in `farm/bot/.env` as `TELEGRAM_BOT_TOKEN=...`. Treat the token like a password: anyone who has it can act as the bot. If it leaks, send `/revoke` to BotFather.
4. Start the bot (below), open your bot in Telegram and send `/start`. If `ALLOWED_CHAT_IDS` is empty, the reply tells you your chat ID. Put it in `.env` as `ALLOWED_CHAT_IDS=<id>` and restart, so nobody else can use the bot.

### `.env` settings

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | (required to run) | From @BotFather. Never printed or logged. |
| `ALLOWED_CHAT_IDS` | empty: anyone | Comma-separated chat IDs. Others are ignored, with no reply. |
| `DAILY_AT` | `09:00` | Daily message time, 24-hour. |
| `TIMEZONE` | `America/Los_Angeles` | Time zone for `DAILY_AT` and the times in messages. |
| `CUTIEFARM_DATA` | `farm/data` | Data folder shared with the camera and sensor programs. |
| `SCAN_COMMAND` | empty | Command for a manual scan, shown when no recent scan exists. |
| `FARM_LAT`, `FARM_LON`, `WATER_BELOW_PCT`, `CITRUS_KC`, `HOLD_OFF_BELOW_MM`, `WEEKLY_FROM_MM`, `TWICE_WEEKLY_FROM_MM` | see below | Watering advice. |

Real environment variables override `.env`. A wrong value stops the bot at startup with a one-line explanation.

## Run

```powershell
farm\bot\.venv\Scripts\python -m farm.bot
```

Run it from the repo root, in its own terminal, next to the camera program and the sensor program. They share only the data folder, so start them in any order. Without a token, the bot exits and tells you how to get one.

Commands in Telegram:

| Command | What it does |
|---|---|
| `/start` | Subscribe this chat to the daily message (saved in `bot_state.json` in the data folder). |
| `/status` | Send the message now. |
| `/water` | Watering advice, with the inputs it used. |
| `/picked 3` | Log 3 oranges picked today. |
| `/removed 1` | Log 1 orange removed today. |
| `/watered` | Log that you watered today. |
| `/undo` | Undo this chat's last harvest log entry. |
| `/week` | Compare the first and latest scans in the last 7 days and see this chat's harvest totals and watering days. |
| `/stop` | Unsubscribe. |
| `/help` | List the commands. |

You can also log completed actions in English or Spanish, such as “I picked 3 oranges,” “quité 1 con hongo,” or “he regado.” Questions still go to the conversation handler.

The bot appends harvest actions to `harvest.jsonl` in `CUTIEFARM_DATA` with `taken_at`, `chat_id`, `kind`, `count` and the original `text`. `/undo` appends an undo marker for the chat's most recent action. Weekly totals exclude undone actions. The original JSONL lines stay on disk.

### Keeping it running on Windows

The daily message only goes out while the bot is running and the laptop is awake. If the bot is down at 9:00, that day's message is skipped; `/status` still works once the bot is back.

- In **Settings > System > Power**, set "When plugged in, put my device to sleep after" to **Never**, and keep the laptop plugged in.
- Leave the terminal window open. Closing it stops the bot.
- To start it at logon, create a Task Scheduler task: Action "Start a program", Program `C:\Users\<you>\Cutiehacksproject\farm\bot\.venv\Scripts\python.exe`, Arguments `-m farm.bot`, Start in `C:\Users\<you>\Cutiehacksproject`. Tick "Run only when user is logged on" so it can reach the data folder.

## Preview without Telegram

`preview` prints the message the bot would send. It needs no token and no network, unless `FARM_LAT`/`FARM_LON` are set and you use real data:

```powershell
farm\bot\.venv\Scripts\python -m farm.bot preview                     # current data folder
farm\bot\.venv\Scripts\python -m farm.bot preview --data D:\demo-data  # another folder
farm\bot\.venv\Scripts\python -m farm.bot preview --fixture mold       # built-in made-up data
farm\bot\.venv\Scripts\python -m farm.bot preview --fixture hot-dry --water   # the /water reply
farm\bot\.venv\Scripts\python -m farm.bot preview --fixture mold --html       # raw Telegram HTML
```

Fixtures: `ripe-heavy`, `mold` (the landing-page example), `empty` (no fruit found), `stale` (last scan 2 days ago), `unripe` (nothing to pick), `sensors-simulated`, and for watering `hot-dry`, `cool-wet`, `soil-low`, `sensors-only` (no forecast, sensor estimate) and `no-data`. The preview header marks fixture output as made-up data.

## Demo tips

- Judges will not wait until 9:00. Send `/status`, `/water` and `/week` live.
- Point `CUTIEFARM_DATA` at a separate demo folder and run `python -m farm.bot seed-demo --week` using the bot's venv. It adds seven days of marked demo scans and example harvest entries. Any chat can see the examples in that folder's `/week` reply.
- Without the camera or the board, run `preview --fixture mold` on the projector, or write a demo data folder with the snippet below and point `CUTIEFARM_DATA` at it.
- Simulated sensor readings are always labelled "(simulated)" in the message. Keep it that way: it is what makes the demo honest.
- Set `DAILY_AT` a couple of minutes ahead and restart the bot to show the scheduled message arriving on its own.

## Watering advice

**This is a rule of thumb with adjustable thresholds, not agronomic advice.** It is meant to tell the grower when to look, not to replace checking the soil by hand.

1. **Soil moisture leads.** If the latest soil reading (no older than 6 hours) is below `WATER_BELOW_PCT` (default 35%), the advice is "Water today".
2. **Cadence from demand.** Otherwise the bot estimates this week's water demand:

   `demand (mm/week) = CITRUS_KC × ET0 over the next 7 days − rain over the next 7 days` (not below 0)

   ET0 is the reference evapotranspiration, and `CITRUS_KC` (default 0.65) is the crop coefficient for mature citrus. The demand maps to a cadence:

   | Weekly demand | Advice |
   |---|---|
   | below `HOLD_OFF_BELOW_MM` (5) | Hold off |
   | below `WEEKLY_FROM_MM` (12) | Every 2 weeks |
   | below `TWICE_WEEKLY_FROM_MM` (25) | Weekly |
   | 25 or more | Twice a week |

   For scale: a mild Los Angeles week in November has an ET0 of about 19 mm (about 12 mm of demand). A hot summer week is around 45 mm (about 29 mm of demand).
3. **Next watering day.** If the soil readings over the last 3 days show it drying out by at least 0.5 points a day, the bot projects the day it crosses the threshold. Otherwise it counts the cadence from today and says so, because it does not know when the trees were last watered.

**Where ET0 comes from**, in order:

1. **Open-Meteo forecast** (`et0_fao_evapotranspiration` and `precipitation_sum`, free, no key), only if both `FARM_LAT` and `FARM_LON` are set. It is fetched at most once a day and cached in `weather_cache.json` in the data folder. If Open-Meteo cannot be reached, a cached forecast up to 3 days old is used (and labelled "offline"). Failing that, the bot uses the sensor estimate. **Privacy:** setting these sends the farm's location, rounded to 2 decimals (about 1 km), to Open-Meteo.
2. **Hargreaves estimate from the sensor temperatures** (FAO-56 eq. 52): `ET0 = 0.0023 × (Tmean + 17.8) × √(Tmax − Tmin) × 0.408 × Ra`, where Ra (the extraterrestrial radiation) comes from the latitude and the date. Fallbacks:
   - Daily low and high come from days whose readings span at least 12 hours (3 readings or more). With no such day yet, the bot uses the mean temperature and assumes a 10 °C daily range.
   - Without `FARM_LAT`, it assumes latitude 34° N (Los Angeles).
   - Hargreaves ignores humidity and wind, so the bot adds 10% for dry air (mean humidity under 40%), subtracts 10% for humid air (over 70%), and adds 10% for wind of 4 m/s or more.
   - There is no rain sensor, so without a forecast, rain is taken as zero.

Every assumption is listed in the `/water` reply under "Based on". If there is no soil reading, no temperature and no forecast, the bot says there is not enough data and how to get it, instead of guessing.

## For the CV/Arduino side

The bot only needs records in the data folder, written with `farm/common/store.py`. The exact fields are in [`farm/CONTRACT.md`](../CONTRACT.md). In short:

- **Scans** (`scans.jsonl`): `taken_at`, `source` (`webcam`/`file`), `model` (any name containing `heuristic` adds the colour-check line), `image`, `fruits` (each with `id`, `label` in `unripe`/`ripening`/`ripe`/`mold`, `confidence` in `high`/`medium`/`low`, `bbox`, `crop`). Save a `crop` image for every `mold` fruit: that is the photo the grower gets. Paths are relative to the data folder. The bot sends only `.jpg`/`.jpeg`/`.png`/`.webp` files inside it.
- **Sensors** (`sensors.jsonl`): `taken_at`, `soil_moisture_pct`, `temperature_c`, `humidity_pct`, `wind_ms`. Use `null` for any sensor that is not connected, and `"simulated": true` for simulator output. For watering advice, write a reading every few minutes, all day: the bot uses the last 7 days.

The bot treats a scan as current for 24 hours and a sensor reading for 1 hour.

```python
from farm.common import store

store.append_scan({
    "id": "20261121T090012-3f9a",
    "source": "webcam",
    "model": "color-heuristic-v1",
    "image": "scans/20261121T090012-3f9a.jpg",
    "fruits": [
        {"id": 1, "label": "ripe", "confidence": "high", "bbox": [412, 220, 96, 98], "crop": None},
        {"id": 2, "label": "mold", "confidence": "medium", "bbox": [130, 300, 90, 92],
         "crop": "scans/20261121T090012-3f9a-2.jpg"},
    ],
})  # fills taken_at and summary

store.append_sensors({
    "soil_moisture_pct": 41.0, "temperature_c": 22.4, "humidity_pct": 55.0, "wind_ms": None,
    "raw": "SOIL=612;T=22.4;H=55", "simulated": True,
})  # fills taken_at
```

Then check what the grower would get: `farm\bot\.venv\Scripts\python -m farm.bot preview`.

## Tests

```powershell
farm\bot\.venv\Scripts\python -m pytest farm\bot\tests -q
```

They cover the composer, watering advice and forecast cache, schedule and config parsing, access control, the photo path check, subscriptions, the handlers (with fake Telegram objects) and the CLI. Nothing in them talks to Telegram or Open-Meteo.

## Files

`compose.py` (message, pure), `irrigation.py` (watering advice, pure), `weather.py` (Open-Meteo and its cache), `app.py` (Telegram handlers and the daily job), `harvest.py` (action parser, harvest log and weekly summary), `config.py`, `access.py`, `state.py`, `fixtures.py`, `__main__.py` (CLI).

## Conversation (free text)

Besides the commands, the bot answers plain questions in the grower's language, for example "¿Y las de la izquierda?" or "When should I water?".

- **Always on: keywords.** English and Spanish words for oranges, ripeness, mold and watering map to the `/status` and `/water` answers (`farm/bot/chat.py`, `keyword_intent`).
- **With `OPENAI_API_KEY` set: an OpenAI model** (default `OPENAI_MODEL=gpt-6-luna`) answers anything else. It only sees a text summary of the latest scan (counts, each orange's label, confidence and rough position in the picture), the latest sensor reading and the watering advice. It is told to answer only from that data and to say when the data is demo or simulated. It keeps the last 6 turns of each chat in memory, so follow-ups work.
- **Limits:** `CHAT_DAILY_LIMIT` questions per chat per day (default 30) and `CHAT_GLOBAL_DAILY_LIMIT` for the whole bot (default 500), because anyone with the landing page's QR code can chat. Past the limit, and whenever the API fails, the bot falls back to keywords.
- **What leaves the laptop:** the question, that chat's recent turns and the farm summary go to OpenAI. Photos never do.

## Photos and instant mold alerts

- **Send the bot a photo of an orange.** It runs the same colour check as the web scanner (`farm/bot/peel.py`, a port of `web/src/scanner/classifier.js`) on the centre of the photo, on the laptop, and replies with the state: unripe, ripening, ready to pick or possible mold. The photo is never sent to OpenAI. If the chat has been talking in another language, the model only rewords the fixed reply into that language.
- **Instant mold alerts.** Every 30 seconds the bot checks for a new scan. If it has possible mold, subscribers get an alert right away, with the photo, instead of waiting for 9:00. The scan that is already there when the bot starts doesn't trigger an alert. Try it with `python -m farm.bot seed-demo`, which writes a new demo scan with one moldy orange.
