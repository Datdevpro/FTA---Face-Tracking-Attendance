@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

cd /d "%~dp0"

echo ============================================================
echo   FTA - Face Tracking Attendance System (Docker Windows)
echo ============================================================
echo.

:: 1. Kiem tra Docker CLI
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Docker!
    echo Vui long cai dat Docker Desktop cho Windows tu: https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)

:: 2. Kiem tra Docker Desktop Daemon dang chay
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Docker Desktop chua duoc bat hoac chua khoi dong xong!
    echo Vui long mo ung dung Docker Desktop tren Windows, cho bieu tuong Docker chuyen sang mau xanh (running), sau do chay lai file nay.
    echo.
    pause
    exit /b 1
)

:: 3. Kiem tra file .env
if not exist ".env" (
    echo [*] Tao file cau hinh .env tu .env.example...
    copy ".env.example" ".env" >nul
)

:: 4. Build va khoi chay Container
echo [*] Dang khoi dong FTA Container qua Docker Compose...
echo [*] Qua trinh build lan dau se mat vai phut de chuan bi thu vien AI...
echo.

docker compose up --build -d

if %errorlevel% neq 0 (
    echo.
    echo [LOI] Khong the khoi dong container! Vui long kiem tra log Docker.
    pause
    exit /b 1
)

echo.
echo [*] Dang kiem tra trang thai he thong...
timeout /t 3 /nobreak >nul

:: Cho den khi he thong san sang (toi da 30 giay)
set ATTEMPTS=0
:WAIT_LOOP
set /a ATTEMPTS+=1
powershell -Command "try { $res = Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 2; if ($res.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto READY

if !ATTEMPTS! geq 15 (
    echo [CANH BAO] He thong dang tiep tuc khoi dong cac model AI trong nen...
    goto SHOW_INFO
)
echo Dang cho service san sang... (!ATTEMPTS!/15)
timeout /t 2 /nobreak >nul
goto WAIT_LOOP

:READY
echo.
echo [THANH CONG] He thong da san sang!

:SHOW_INFO
echo ============================================================
echo   FTA System da khoi dong thanh cong!
echo ============================================================
echo   Dashboard:   http://localhost:8000
echo   API Docs:    http://localhost:8000/docs
echo   Tai khoan:   admin
echo   Mat khau:    admin123
echo ============================================================
echo.
echo Dang mo Dashboard tren trinh duyet...
start http://localhost:8000

echo.
echo De dung he thong, ban co the chay file: stop.bat
echo.
pause
