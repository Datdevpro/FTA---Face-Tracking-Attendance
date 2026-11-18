@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if "%DEBUG%"=="" set "DEBUG=true"

"%PYTHON_EXE%" -m scripts.start_go2rtc
if errorlevel 1 echo WARNING: FTA will start, but camera audio may be unavailable.
"%PYTHON_EXE%" -m scripts.start_vieneu
if errorlevel 1 echo WARNING: VieNeu unavailable; Edge TTS will be used.

echo Starting FTA server...
echo Dashboard: http://localhost:1900
echo API Docs:  http://localhost:1900/docs
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 1900

endlocal
