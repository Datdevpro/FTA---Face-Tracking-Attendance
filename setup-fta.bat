@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title FTA Setup

rem Use the project .env during setup instead of inherited machine settings.
set "DEBUG="
set "FACE_ONNX_PROVIDER="
set "ANTI_SPOOFING_PROVIDER="

echo ============================================================
echo   FTA - Automatic Setup for Windows
echo ============================================================
echo.

set "PYTHON_CMD="

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import struct, sys; raise SystemExit(0 if struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import struct, sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3.11 64-bit was not found.
    echo.
    echo Install Python 3.11 from:
    echo https://www.python.org/downloads/release/python-3119/
    echo.
    echo During installation, select "Add python.exe to PATH", then run
    echo this file again.
    goto :failed
)

echo [1/7] Python 3.11 64-bit found.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] The existing venv was created with an unsupported Python version.
        echo Rename or remove the venv folder, then run this setup again.
        goto :failed
    )
    echo [2/7] Existing virtual environment found.
) else (
    echo [2/7] Creating virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 goto :venv_failed
)

if exist ".env" (
    echo [3/7] Existing .env configuration preserved.
) else (
    if not exist ".env.example" (
        echo [ERROR] .env.example is missing.
        goto :failed
    )
    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 goto :env_failed
    "venv\Scripts\python.exe" -c "from pathlib import Path; import secrets; p=Path('.env'); text=p.read_text(encoding='utf-8'); text=text.replace('JWT_SECRET_KEY=your-super-secret-key-change-this-in-production', 'JWT_SECRET_KEY=' + secrets.token_hex(32)); p.write_text(text, encoding='utf-8')"
    if errorlevel 1 goto :env_failed
    echo [3/7] Created .env with CPU inference enabled.
)

echo [4/7] Updating Python package tools...
"venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :dependency_failed

if exist "model_wheel\insightface-0.7.3-cp311-cp311-win_amd64.whl" (
    echo [5/7] Installing the bundled InsightFace package...
    "venv\Scripts\python.exe" -m pip install "model_wheel\insightface-0.7.3-cp311-cp311-win_amd64.whl"
    if errorlevel 1 goto :dependency_failed
) else (
    echo [ERROR] The bundled InsightFace wheel is missing.
    goto :failed
)

echo       Installing project dependencies. This can take several minutes...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :dependency_failed
"venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto :dependency_failed

if not exist "data\models\anti_spoofing\AntiSpoofing_bin_1.5_128.onnx" (
    echo [ERROR] The anti-spoofing model is missing from the repository.
    goto :failed
)

echo [6/7] Creating the local database and default account...
"venv\Scripts\python.exe" -m scripts.init_db
if errorlevel 1 goto :database_failed

echo [7/7] Preparing the face recognition model...
echo       The first download is about 300 MB. Please keep Internet connected.
"venv\Scripts\python.exe" -c "from app.config import settings; from app.services.face_recognition import FaceRecognitionService; service = FaceRecognitionService(settings.FACE_MODEL_NAME, settings.MODELS_DIR, onnx_provider='cpu'); service.initialize(); print('Face recognition model is ready.')"
if errorlevel 1 goto :model_failed

echo.
echo ============================================================
echo   FTA setup completed successfully.
echo ============================================================
echo.
echo Login:    admin / admin123
echo Start:    Double-click start-fta.bat
echo Website:  http://localhost:8000
echo.
pause
exit /b 0

:venv_failed
echo [ERROR] Could not create the Python virtual environment.
goto :failed

:env_failed
echo [ERROR] Could not create .env from .env.example.
goto :failed

:dependency_failed
echo [ERROR] A Python package could not be installed.
echo Check your Internet connection and run setup-fta.bat again.
goto :failed

:database_failed
echo [ERROR] Database initialization failed.
goto :failed

:model_failed
echo [ERROR] The face recognition model could not be prepared.
echo Check your Internet connection and run setup-fta.bat again.
goto :failed

:failed
echo.
echo Setup did not complete. Review the error above, then run this file again.
echo.
pause
exit /b 1
