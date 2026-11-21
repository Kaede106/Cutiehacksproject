# CutieFarm camera runner

From the repository root, activate the shared bot virtual environment or use its Python executable. Install the pinned dependencies into that environment:

```powershell
python -m pip install -r farm/bot/requirements.txt
```

The OpenCV and Ultralytics dependencies were installed in the shared Windows x64 Python 3.14 environment. The runner reads `CUTIEFARM_DATA` from the environment or `farm/bot/.env` and defaults to `farm/data`. Set a separate folder when testing so the running demo keeps its own data.

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

## Choose a detector

The runner defaults to YOLO when Ultralytics can be imported and the bundled `ml/image-classification/yolo26n.pt` weights are present. It loads the weights once per process and uses the model's COCO `orange` class to propose fruit boxes. The bot's colour heuristic classifies ripeness inside each box. If the weights or dependency are unavailable, the runner prints one notice and uses the colour detector.

```powershell
python -m farm.vision scan --image path.jpg --detector yolo
python -m farm.vision watch --detector yolo --yolo-weights path/to/weights.pt --min-conf 0.35
python -m farm.vision live --detector color
```

`--detector yolo` requires local weights with an `orange` class and a working Ultralytics installation. It reports a configuration error if either is unavailable. `--min-conf` sets the YOLO detection threshold (default `0.35`).

## Hub and Telegram bot

```powershell
python -m farm --vision
```

This starts `python -m farm.vision watch` as the hub's `vision` part. Set `VISION_COMMAND` in `farm/bot/.env` or the environment to override it, for example `VISION_COMMAND="python -m farm.vision watch --every 30s --camera 1"`. Hub output for this part goes to `logs/vision.log` in the shared data folder. Point the watcher and the bot at the same `CUTIEFARM_DATA` folder for a connected demo.

Each saved scan appends one record through `store.append_scan` and saves the full JPEG under `scans/` in the shared folder. Each fruit has a bounding box and `crop: null`. The bot reads the records for its daily update. See the [scan contract](../CONTRACT.md) for the record format.

## Use a different classifier

```powershell
python -m farm.vision scan --image path.jpg --classifier my_model:classify
```

Make the module importable in the shared environment. Its function takes a NumPy bounding-box crop in RGB order with shape `(height, width, 3)`, dtype `uint8` and values from 0 to 255. It returns `(label, confidence_level, scores)` using:

- A label of `unripe`, `ripening` or `ripe`. Return `none` to skip a candidate.
- A confidence level of `high`, `medium` or `low`.
- A mapping with a finite numeric score for each of the three ripeness labels.

With the built-in classifier, the record's `model` is `yolo-orange+color-heuristic-v1` for YOLO or `color-heuristic-v1` for the colour detector. A custom classifier replaces the `color-heuristic-v1` part with the supplied `module:function` in either case.

## Limitations

With the colour detector, green leaves can read as unripe oranges and overlapping fruit can share one box. YOLO may miss small, occluded or unusually coloured oranges. Lighting, white balance and glare can shift labels with either detector. A plain gray background and consistent diffuse light help. The ripeness classifier sees only the exposed peel and can skip a box when it sees very little peel.
