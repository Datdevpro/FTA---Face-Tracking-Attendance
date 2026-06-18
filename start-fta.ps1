param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8000,
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

Write-Host "Starting FTA server..." -ForegroundColor Cyan
Write-Host "Dashboard: http://localhost:$Port" -ForegroundColor Green
Write-Host "API Docs:  http://localhost:$Port/docs" -ForegroundColor Green
Write-Host ""

& $PythonExe -m uvicorn app.main:app @ReloadArgs --host $HostName --port $Port
