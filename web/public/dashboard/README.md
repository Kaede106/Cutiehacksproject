# Control room demo snapshot

Vite copies this folder into the build, and Vercel serves it at `/dashboard/`. It is a static copy of the CutieFarm control room made from **demo data**, not from the farm. The live control room runs only on the farm laptop (`farm/dashboard/README.md`).

`index.html`, `app.js`, `app.css`, `state.json` and `scans/` are generated. Do not edit them by hand; this README is the only file written by hand. The page is `farm/dashboard/static/`, and the banner on it says it is a demo snapshot.

## Regenerate

From the repository root, in PowerShell, with the shared bot virtual environment. Use a temporary data folder, never `farm/data-demo` (the live bot uses it) or `farm/data`:

```powershell
$py = "<path to the shared venv>\Scripts\python.exe"
$env:CUTIEFARM_DATA = Join-Path $env:TEMP "cutiefarm-public-demo"
Remove-Item -Recurse -Force $env:CUTIEFARM_DATA -ErrorAction SilentlyContinue
& $py -m farm.bot seed-demo --week
& $py -m farm.sensors simulate --count 30 --every 1s
& $py -m farm.vision scan --image web/public/grove.jpg
& $py -m farm.dashboard export --out web/public/dashboard --base-url /dashboard/ --home-url /
```

In Git Bash, set `MSYS_NO_PATHCONV=1` first, or Git rewrites `/dashboard/` into a Windows path.

- `seed-demo --week` writes demo scans (marked `demo`) and example harvest activity. `simulate` writes 30 readings marked `simulated`. `vision scan` runs the camera program on the licensed hero photo (credits in `web/public/CREDITS.md`) and saves one real scan with boxes. The photo is the only image that is exported, as `scans/<id>.jpg`.
- Without the YOLO weights (`ml/image-classification/yolo26n.pt`), the camera program falls back to its colour detector, which can box leaves and merge oranges. The boxes on the snapshot are whatever the detector found.
- Check `state.json` and `scans/` before committing: everything in them is published. Then `cd web && npm run build` and open `/dashboard/` with `npx vite preview`.
- Merging to `main` publishes it, because Vercel builds `web/`.
