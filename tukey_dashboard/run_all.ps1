# Refresh every input and rebuild the Tukey dashboard.
# Usage (PowerShell, from anywhere):  & "C:\Users\matia\Documents\DATATHON\tukey_dashboard\run_all.ps1"
# After the final (Sun 15 Nov, from 12:05 CET) the same command adds the "Final" period automatically.
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root ".venv\Scripts\python.exe"
Set-Location $root

Write-Host "1/5 public leaderboard API (hourly + 15-min windows)"
& $py pipeline\fetch_api.py --step 3600 --by model
& $py pipeline\fetch_api.py --step 900 --by model
& $py pipeline\build_api_tables.py

Write-Host "2/5 RawTree DB, practice period (read-only SELECTs)"
& $py pipeline\extract_db.py --period practice

$nowUtc = (Get-Date).ToUniversalTime()
if ($nowUtc -ge [datetime]"2026-11-15T09:10:00") {
    Write-Host "3/5 RawTree DB, final period"
    & $py pipeline\extract_db.py --period final
} else {
    Write-Host "3/5 final period not started yet: skipped"
}

Write-Host "4/5 derived dataset"
& $py pipeline\build_dataset.py

Write-Host "5/5 render (offline single file + CDN variant)"
& $py pipeline\render.py
& $py pipeline\render.py --cdn
Write-Host "Done: $root\dist\index.html"
