# CutieFarm control room

A live, read-only dashboard for the big screen. It shows the latest camera frame with each orange boxed and labelled, how many are ready to pick, the watering advice with soil, temperature and humidity over the last 24 hours, and an activity feed.

```powershell
farm\bot\.venv\Scripts\python -m farm.dashboard --port 8800   # then open http://127.0.0.1:8800
farm\bot\.venv\Scripts\python -m farm --dashboard             # the same, started by the hub with the other parts
```

`--host 0.0.0.0` shows it on other devices on the LAN. Anyone on the network can then see the farm data, and the program says so when it starts.

## What it reads

Only the shared data folder (`CUTIEFARM_DATA`, see [../CONTRACT.md](../CONTRACT.md)): `scans.jsonl` with `scans/*`, `sensors.jsonl` and `harvest.jsonl`. It never writes there and never creates the folder. The watering advice is `farm.bot.irrigation.advise`, with the bot's settings. The forecast is used only if the bot has already cached it today (`weather_cache.json`); the dashboard never calls Open-Meteo.

The page shows ripeness only: unripe, ripening and ready to pick (`ripe`). The `mold` label and the `crop` field are ignored. A scan with `demo: true` and a sensor reading with `simulated: true` are labelled as such on the page.

## Safety

- GET and HEAD only. The files it serves are the page's three static assets and images directly under `<data>/scans/` (flat file names, `.jpg`, `.jpeg`, `.png`, `.webp`; no slashes, `..` or absolute paths, and no symlink out of `scans/`).
- It reads only `CUTIEFARM_DATA`, `TIMEZONE` and the watering settings from `farm/bot/.env`. The Telegram token and the other keys in that file are never loaded, and the hub starts it without them.
- On loopback it answers only requests addressed to `localhost`, `127.0.0.1` or `[::1]`.

## Files

| File | What it does |
|---|---|
| `state.py` | Builds the JSON for `/api/state` from the data folder, and the image path guard. |
| `server.py` | The threaded `http.server` handler. |
| `settings.py` | Loads the few settings it needs. |
| `static/` | The page: `index.html`, `app.css`, `app.js`. It polls every 2.5 s and updates in place. |
