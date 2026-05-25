@echo off
REM ============================================================
REM  NarayanAstroReader — Frontend rebuild script
REM  Run this from Windows whenever React source files change.
REM  Double-click this file OR run from Command Prompt.
REM ============================================================

echo.
echo  [BUILD] NarayanAstroReader Frontend
echo  =====================================

cd /d "%~dp0frontend-react"

echo  [1/2] Installing dependencies...
call npm install
if errorlevel 1 (
    echo  [ERROR] npm install failed. Is Node.js installed?
    pause
    exit /b 1
)

echo.
echo  [2/2] Building for production...
call npm run build
if errorlevel 1 (
    echo  [ERROR] Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo  =============================================
echo  [OK] Build complete! Restart the backend
echo       server to serve the updated frontend.
echo  =============================================
echo.
pause
