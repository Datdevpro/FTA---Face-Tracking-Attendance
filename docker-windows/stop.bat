@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   FTA - Dung he thong Docker
echo ============================================================
echo.

docker compose down

echo.
echo He thong da duoc dung an toan. Du lieu cham cong va hinh anh van duoc luu tai thu muc data/.
echo.
pause
