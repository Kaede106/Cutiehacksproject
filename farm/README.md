# CutieFarm on the laptop

One command starts everything that runs on the laptop:

```powershell
farm\bot\.venv\Scripts\python -m farm                     # bot + Arduino bridge
farm\bot\.venv\Scripts\python -m farm --simulate-sensors  # bot + simulated sensor readings (demo without the board)
farm\bot\.venv\Scripts\python -m farm status              # what the data folder says right now
```

```
webcam ─► vision program (VISION_COMMAND) ─► scans.jsonl ───┐
                                                            ├─► bot: 9:00 message, mold alerts,
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
- [`common/store.py`](common/store.py): the only code that reads and writes the shared files.
