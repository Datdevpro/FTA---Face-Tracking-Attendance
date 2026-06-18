@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if "%DEBUG%"=="" set "DEBUG=true"

echo Starting FTA server...
echo Dashboard: http://localhost:8000
echo API Docs:  http://localhost:8000/docs
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

endlocal
