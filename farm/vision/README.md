# CutieFarm camera runner

From the repository root, activate the shared bot virtual environment or use its Python executable. Install the pinned dependencies into that environment:

```powershell
python -m pip install -r farm/bot/requirements.txt
```

The OpenCV pin has a Windows x64 wheel compatible with Python 3.14. The runner reads `CUTIEFARM_DATA` from the environment or `farm/bot/.env` and defaults to `farm/data`. Set a separate folder when testing so the running demo keeps its own data.

```powershell
$env:CUTIEFARM_DATA = Join-Path $env:TEMP "cutiefarm-vision-test"
python -m farm.vision scan --camera 0
python -m farm.vision scan --image path.jpg
python -m farm.vision watch --every 2m --camera 0
python -m farm.vision live --camera 0
```

- `scan` saves one scan. The default camera index is `0`. Use `--image` to scan a saved photo through the same detector.
- `watch` scans immediately and repeats every two minutes by default. It releases the camera between scans. Stop it with Ctrl+C.
- `live` draws boxes and labels in an OpenCV window. Focus the window and press **S** to save the displayed scan or **Q** to quit. The saved photo has no overlays.

The webcam streams for about one second before the first reading so exposure can settle. If the camera is unavailable, check the index, camera permissions and whether another app is using it. Stop the hub's watcher before starting the live preview if they share a camera.

## Hub and Telegram bot

```powershell
python -m farm --vision
```

This starts `python -m farm.vision watch` as the hub's `vision` part. Set `VISION_COMMAND` in `farm/bot/.env` or the environment to override it, for example `VISION_COMMAND="python -m farm.vision watch --every 30s --camera 1"`. Hub output for this part goes to `logs/vision.log` in the shared data folder. Point the watcher and the bot at the same `CUTIEFARM_DATA` folder for a connected demo.

Each saved scan appends one record through `store.append_scan`. The runner saves the full JPEG and any mold crops under `scans/` in the shared folder. The bot reads the records for its daily update and mold alerts. See the [scan contract](../CONTRACT.md) for the record format.

## Use a different classifier

```powershell
python -m farm.vision scan --image path.jpg --classifier my_model:classify
```

Make the module importable in the shared environment. Its function takes a NumPy bounding-box crop in RGB order with shape `(height, width, 3)`, dtype `uint8` and values from 0 to 255. It returns `(label, confidence_level, scores)` using:

- A label of `unripe`, `ripening`, `ripe` or `mold`. Return `none` to skip a candidate.
- A confidence level of `high`, `medium` or `low`.
- A mapping with a finite numeric score for each of the four fruit labels.

The saved `model` is `color-heuristic-v1` by default or the supplied `module:function` for a custom classifier. The plug-in classifies crops found by the same colour-based detector.

## Limitations

Green leaves can read as unripe oranges. Lighting, white balance and glare can shift labels or hide mold patches. A plain gray background and consistent diffuse light help. Fruit that overlap heavily or differ greatly in size may share one box. The camera sees only the exposed peel, and mold labels are heuristic estimates.
