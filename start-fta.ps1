param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 1900,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

if (-not $env:DEBUG) {
    $env:DEBUG = "true"
}

$ReloadArgs = @()
if (-not $NoReload) {
    $ReloadArgs = @("--reload")
}

& $PythonExe -m scripts.start_go2rtc
if ($LASTEXITCODE -ne 0) {
    Write-Warning "FTA will start, but camera audio may be unavailable."
}

Write-Host "Starting FTA server..." -ForegroundColor Cyan
& $PythonExe -m scripts.start_vieneu
if ($LASTEXITCODE -ne 0) {
    Write-Warning "VieNeu unavailable; Edge TTS will be used."
}
Write-Host "Dashboard: http://localhost:$Port" -ForegroundColor Green
Write-Host "API Docs:  http://localhost:$Port/docs" -ForegroundColor Green
Write-Host ""

& $PythonExe -m uvicorn app.main:app @ReloadArgs --host $HostName --port $Port
