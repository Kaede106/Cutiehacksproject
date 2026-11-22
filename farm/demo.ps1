# CutieFarm pitch demo: one command on the presenter's laptop (Windows).
#
#   powershell -ExecutionPolicy Bypass -File farm\demo.ps1               # demo data + simulated sensors
#   powershell -ExecutionPolicy Bypass -File farm\demo.ps1 -Camera       # + the webcam scanning real oranges
#   powershell -ExecutionPolicy Bypass -File farm\demo.ps1 -Arduino      # real sensors from the board instead of simulated
#   powershell -ExecutionPolicy Bypass -File farm\demo.ps1 -InstallOnly  # do the slow install now, start nothing
#
# Starts the Telegram bot, the sensors (simulated or the Arduino), the control room dashboard and,
# with -Camera, the camera program. It opens the dashboard and the landing page in the browser.
# Needs Python 3.12+ on PATH and farm\bot\.env with the bot token (share it privately; never commit it).
# Stop the bot on every other laptop first: two bots with the same token fight over the messages.

param([switch]$Camera, [switch]$Arduino, [switch]$InstallOnly, [switch]$FreshData)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$venv = 'farm\bot\.venv'
$py = "$venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host 'Creating the virtual environment...'
    python -m venv $venv
}
Write-Host 'Installing dependencies (the first time this downloads YOLO and torch, which takes several minutes)...'
& $py -m pip install -q -r farm\bot\requirements.txt
if ($InstallOnly) { Write-Host 'Installed. Run this script again without -InstallOnly to start the demo.'; exit 0 }

if (-not (Test-Path 'farm\bot\.env')) {
    Copy-Item 'farm\bot\.env.example' 'farm\bot\.env'
    Write-Host 'Created farm\bot\.env. Put TELEGRAM_BOT_TOKEN (and OPENAI_API_KEY) in it, then run this script again.'
    exit 1
}

# A separate data folder for the pitch, so the demo never mixes with real data.
# With -Camera the folder starts empty: every scan in it comes from the webcam, never from demo data,
# and the first scan that sees ripe oranges triggers the bot's ready-to-pick alert.
$data = Join-Path (Get-Location) $(if ($Camera) { 'farm\data-pitch-camera' } else { 'farm\data-pitch' })
$env:CUTIEFARM_DATA = $data
if (($FreshData -or $Camera) -and (Test-Path $data)) {
    Remove-Item -Recurse -Force (Join-Path $data '*') -Exclude 'bot_state.json'
}
if (-not $Camera -and -not (Test-Path (Join-Path $data 'scans.jsonl'))) {
    Write-Host 'Writing a week of demo data (clearly marked as demo)...'
    & $py -m farm.bot seed-demo --week
}

$hubArgs = @('-m', 'farm', '--dashboard')
if (-not $Arduino) { $hubArgs += '--simulate-sensors' } else { & $py -m farm.sensors ports }

if ($Camera) {
    # The live window owns the webcam: it shows YOLO's boxes and labels in real time, and S saves a scan
    # (which the dashboard and the bot pick up within seconds). No background watcher, so the camera isn't shared.
    Start-Process -FilePath $py -ArgumentList '-m', 'farm.vision', 'live' -WorkingDirectory (Get-Location)
}
Start-Job -ScriptBlock { Start-Sleep 6; Start-Process 'http://127.0.0.1:8800'; Start-Process 'https://cutiehacksproject.vercel.app' } | Out-Null
Write-Host ''
Write-Host 'Dashboard: http://127.0.0.1:8800   Bot: https://t.me/CutieFarmGroveBot   Ctrl+C stops everything.'
if ($Camera) { Write-Host 'Camera window: point it at the oranges, press S to save a scan, Q to close it.' }
& $py @hubArgs
