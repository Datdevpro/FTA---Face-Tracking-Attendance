@echo off
setlocal
cd /d "%~dp0"
set "FTA_PYTHON=%CD%\venv\Scripts\python.exe"
if not exist "%FTA_PYTHON%" set "FTA_PYTHON=python"
if not exist ".venv-vieneu\Scripts\python.exe" (
    "%FTA_PYTHON%" -m venv .venv-vieneu
    if errorlevel 1 exit /b 1
)
".venv-vieneu\Scripts\python.exe" -m pip install -r requirements-vieneu.txt
if errorlevel 1 exit /b 1
echo VieNeu installed. Start FTA to load the model; first run needs Internet.
endlocal
