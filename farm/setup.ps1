# Set up CutieFarm on a Windows laptop and start it.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File farm\setup.ps1
# Needs Python 3.12+ on PATH, and farm\bot\.env with TELEGRAM_BOT_TOKEN (ask the team; never commit it).

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$venv = 'farm\bot\.venv'
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host 'Creating the virtual environment...'
    python -m venv $venv
}
Write-Host 'Installing dependencies...'
& "$venv\Scripts\python.exe" -m pip install -q -r farm\bot\requirements.txt

if (-not (Test-Path 'farm\bot\.env')) {
    Copy-Item 'farm\bot\.env.example' 'farm\bot\.env'
    Write-Host ''
    Write-Host 'Created farm\bot\.env from the example. Put TELEGRAM_BOT_TOKEN (and OPENAI_API_KEY) in it, then run this script again.'
    exit 1
}

Write-Host 'Serial ports (the Arduino should be one of them):'
& "$venv\Scripts\python.exe" -m farm.sensors ports
Write-Host ''
Write-Host 'Starting CutieFarm. Stop the bot on any other laptop first: one bot per token.'
& "$venv\Scripts\python.exe" -m farm @args
