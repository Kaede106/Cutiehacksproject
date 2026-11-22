# CutieFarm on the laptop

CutieFarm tells the grower which oranges are ready to pick and when the grove needs water.

**New laptop (Windows):** from the repo root, run `powershell -ExecutionPolicy Bypass -File farm\setup.ps1` (add `--simulate-sensors` to use simulated sensor data). It creates the venv, installs everything, checks `farm/bot/.env`, lists the serial ports and starts the hub. Run the bot on only one laptop at a time.

## Pitch demo on the presenter's laptop

1. **Well before the pitch** (it downloads YOLO and torch): `powershell -ExecutionPolicy Bypass -File farm\demo.ps1 -InstallOnly`
2. Copy `farmot\.env` to that laptop privately (USB or a direct message). Never commit it.
3. Stop the bot on every other laptop: one bot per token.
4. Start it: `powershell -ExecutionPolicy Bypass -File farm\demo.ps1`. Add `-Camera` to scan real oranges with the webcam, and `-Arduino` if the board is plugged in. It uses its own data folder, `farm\data-pitch`, seeds clearly marked demo data, starts the bot, the sensors and the control room, and opens the dashboard and the landing page.
5. For a live camera window with boxes, open a second terminal: `farmot\.venv\Scripts\python -m farm.vision live`

One command starts everything that runs on the laptop:

```powershell
farm\bot\.venv\Scripts\python -m farm                     # bot + Arduino bridge
farm\bot\.venv\Scripts\python -m farm --simulate-sensors  # bot + simulated sensor readings (demo without the board)
farm\bot\.venv\Scripts\python -m farm status              # what the data folder says right now
```

```
webcam ─► vision program (VISION_COMMAND) ─► scans.jsonl ───┐
                                                            ├─► bot: 9:00 message, ready-to-pick alerts,
Arduino ─USB─► sensor bridge (farm/sensors) ─► sensors.jsonl┘      watering advice, chat, photos
```

The hub starts each part as its own process. It restarts a part that crashes, unless it keeps crashing or exits with a settings error. Each part's output goes to `<data folder>/logs/<part>.log`, and the terminal shows one status screen: whether each part is running, the last line of its log, the age of the last scan and sensor reading, and how many chats are subscribed. Ctrl+C stops everything.

The parts never call each other. They share files in the data folder, as described in [CONTRACT.md](CONTRACT.md). So any part can be missing or down and the others keep working.

## Settings (in `farm/bot/.env`, read by every part)

| Variable | What it does |
|---|---|
| `CUTIEFARM_DATA` | The shared data folder. Use `farm/data-demo` for the demo, and the real folder once the camera writes scans. |
| `SENSORS_ARGS` | Extra arguments for the bridge, e.g. `--port COM3 --soil-dry 610 --soil-wet 290` (see `farm/sensors/README.md`). |
| `VISION_COMMAND` | The command that runs the camera program, if there is one. It must write scans with `store.append_scan` (see `farm/bot/README.md`). |

Run only one bot at a time with the same token: two bots polling Telegram at once fight over the messages.

## Parts

- [`bot/`](bot/README.md): the Telegram bot.
- [`sensors/`](sensors/README.md): the Arduino serial bridge and a reference sketch for the board.
- [`dashboard/`](dashboard/README.md): the read-only control room for the big screen (`python -m farm --dashboard`).
- [`common/store.py`](common/store.py): the only code that reads and writes the shared files.
