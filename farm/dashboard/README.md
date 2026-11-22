# CutieFarm control room

A live, read-only dashboard for the big screen. It shows the latest camera frame with each orange boxed and labelled, how many are ready to pick, the watering advice with soil, temperature and humidity over the last 24 hours, and an activity feed.

```powershell
farm\bot\.venv\Scripts\python -m farm.dashboard --port 8800   # then open http://127.0.0.1:8800
farm\bot\.venv\Scripts\python -m farm --dashboard             # the same, started by the hub with the other parts
```

`--host 0.0.0.0` shows it on other devices on the LAN. Anyone on the network can then see the farm data, and the program says so when it starts.

The live control room runs only on the farm laptop. It reads the local data folder and is never exposed to the internet. The public website has a static demo copy instead, see "Static snapshot" below.

## What it reads

Only the shared data folder (`CUTIEFARM_DATA`, see [../CONTRACT.md](../CONTRACT.md)): `scans.jsonl` with `scans/*`, `sensors.jsonl` and `harvest.jsonl`. It never writes there and never creates the folder. The watering advice is `farm.bot.irrigation.advise`, with the bot's settings. The forecast is used only if the bot has already cached it today (`weather_cache.json`); the dashboard never calls Open-Meteo.

The page shows ripeness only: unripe, ripening and ready to pick (`ripe`). The `mold` label and the `crop` field are ignored. A scan with `demo: true` and a sensor reading with `simulated: true` are labelled as such on the page.

## Static snapshot (the public demo)

```powershell
$env:CUTIEFARM_DATA = "<a demo data folder, not the live one>"
farm\bot\.venv\Scripts\python -m farm.dashboard export --out <dir>
farm\bot\.venv\Scripts\python -m farm.dashboard export --out web\public\dashboard --base-url /dashboard/ --home-url /
```

`export` writes a self-contained copy of the page to `<dir>`: `index.html`, `app.js`, `app.css`, `state.json` (built by the same `state.build_state` that serves `/api/state`, plus a `snapshot` entry with the date) and the one scan image the page shows, under `<dir>/scans/`. It reads the data folder and writes nothing there. `--out` must not be the data folder, inside it or above it.

- The exported `index.html` carries `<meta name="cutiefarm-mode" content="static">`. With it, `app.js` reads `./state.json` once instead of polling `/api/state`, shows times as dates and clocks (never "5 min ago"), and the page shows a banner: "Demo snapshot of the CutieFarm control room, made from demo data on <date>. The live version runs on the farm laptop." The demo and simulated labels stay.
- The scan image goes through the same path guard as the live server (a flat image file directly under `<data>/scans/`, no symlink out). Nothing else is copied: no other scan, no `.jsonl`, no `.env`, no bot state. Images from an earlier export in `<dir>/scans/` are removed first; other files in `<dir>` are left alone.
- `--base-url` writes `<base href>` so the page also works at `/dashboard` without the trailing slash. `--home-url` adds a link back to the landing page in the banner. Both take a plain site path.
- Point `CUTIEFARM_DATA` at a demo folder before exporting, because everything the page shows is published. `web/public/dashboard/README.md` has the recipe for the website.

## Safety

- GET and HEAD only. The files it serves are the page's three static assets and images directly under `<data>/scans/` (flat file names, `.jpg`, `.jpeg`, `.png`, `.webp`; no slashes, `..` or absolute paths, and no symlink out of `scans/`).
- It reads only `CUTIEFARM_DATA`, `TIMEZONE` and the watering settings from `farm/bot/.env`. The Telegram token and the other keys in that file are never loaded, and the hub starts it without them.
- On loopback it answers only requests addressed to `localhost`, `127.0.0.1` or `[::1]`.

## Files

| File | What it does |
|---|---|
| `state.py` | Builds the JSON for `/api/state` from the data folder, and the image path guard. |
| `server.py` | The threaded `http.server` handler. |
| `export.py` | `python -m farm.dashboard export`: the static snapshot for the public site. |
| `settings.py` | Loads the few settings it needs. |
| `static/` | The page: `index.html`, `app.css`, `app.js`. Live, it polls every 2.5 s and updates in place; in a snapshot it reads `state.json` once. |
