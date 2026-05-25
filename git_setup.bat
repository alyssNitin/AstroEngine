@echo off
REM ============================================================
REM  NarayanAstroReader — one-time Git initialisation script
REM  Double-click this file from Windows Explorer to run it.
REM ============================================================
setlocal EnableDelayedExpansion

set "REPO=%~dp0"
set "ASTRO_REMOTE=https://github.com/alyssNitin/AstroEngine.git"
set "PYJHORA_REMOTE=https://github.com/alyssNitin/PyJHora.git"

REM ── Read PYJHORA_PATH from .env ───────────────────────────────────────────────
set "PYJHORA="
if exist "%REPO%.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%REPO%.env") do (
        set "KEY=%%A"
        set "KEY=!KEY: =!"
        if /i "!KEY!"=="PYJHORA_PATH" (
            set "PYJHORA=%%B"
        )
    )
)

REM Strip trailing \src if present (git repo root is one level above src)
if defined PYJHORA (
    if /i "!PYJHORA:~-4!"=="\src" set "PYJHORA=!PYJHORA:~0,-4!"
)

REM Fallback if .env not found or key missing
if not defined PYJHORA (
    set "PYJHORA=C:\Users\ntalu\PyJHora"
    echo WARNING: PYJHORA_PATH not found in .env — using default: !PYJHORA!
) else (
    echo Read PYJHORA_PATH from .env: !PYJHORA!
)

echo.
echo ============================================================
echo  Step 1: Clean any stale .git and initialise fresh repo
echo ============================================================
cd /d "%REPO%"

if exist ".git" (
    echo Removing stale .git folder...
    rmdir /s /q ".git"
)

git init
if %errorlevel% neq 0 (
    echo ERROR: git init failed. Is Git installed?
    echo Download from https://git-scm.com/download/win
    pause
    exit /b 1
)

git branch -M main

echo.
echo ============================================================
echo  Step 2: Configure git identity
echo ============================================================
git config user.email "ntaluja2025@gmail.com"
git config user.name "Narayan Taluja"

echo.
echo ============================================================
echo  Step 3: Stage all project files (respecting .gitignore)
echo ============================================================
git add .
echo.
echo Files staged:
git status --short

echo.
echo ============================================================
echo  Step 4: Create initial commit
echo ============================================================
git commit ^
  -m "Initial commit: full AstroEngine monolith" ^
  -m "Backend (FastAPI + PostgreSQL): Auth with JWT/OAuth/MFA, Kundli engine with PyJHora place-name fix, Claude AI predictions and SSE deep reading, region-aware wallet and payment gateway, admin panel, Redis cache, Celery, Prometheus." ^
  -m "Frontend (React 18 + Vite): Full reading flow, wallet modal with txn_type history fix and mock top-up, i18n EN/HI/TA, auth screens." ^
  -m "Infra: dasha-engine, notification-service, analytics-service microservices, docker-compose, GitHub Actions CI/CD, Locust load tests, pytest suite."

if %errorlevel% neq 0 (
    echo ERROR: Commit failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Step 5: Add remote and push AstroEngine to GitHub
echo ============================================================
git remote add origin %ASTRO_REMOTE%
echo Pushing to %ASTRO_REMOTE% ...
git push --force -u origin main

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Push failed. Common causes:
    echo   1. Not authenticated — use a Personal Access Token as password:
    echo      https://github.com/settings/tokens
    echo   2. No push access to alyssNitin/AstroEngine.
    pause
    exit /b 1
)
echo AstroEngine pushed successfully.

echo.
echo ============================================================
echo  Step 6: Commit and push PyJHora bug-fix
echo           Path: !PYJHORA!
echo ============================================================
if exist "!PYJHORA!\.git" (
    cd /d "!PYJHORA!"
    git config user.email "ntaluja2025@gmail.com"
    git config user.name "Narayan Taluja"
    git add src/jhora/utils.py src/jhora/const.py src/jhora/data/world_cities_with_tz.csv
    git commit ^
      -m "Fix: place_name with more than 1 comma crashes utils.get_location()" ^
      -m "split(',') into bare 2-var destructure crashed for names like 'Mumbai, Maharashtra, India'. Fixed to always take first token as city and last token as country."
    git remote remove origin 2>nul
    git remote add origin %PYJHORA_REMOTE%
    echo Pushing to %PYJHORA_REMOTE% ...
    git push --force -u origin master
    if %errorlevel% neq 0 (
        echo ERROR: PyJHora push failed. Check access to alyssNitin/PyJHora.
    ) else (
        echo PyJHora pushed successfully.
    )
) else (
    echo.
    echo ERROR: No .git folder found at !PYJHORA!
    echo        Check that PYJHORA_PATH in .env points to the PyJHora root folder.
    echo        Current value: !PYJHORA!
)

echo.
echo ============================================================
echo  ALL DONE!
echo.
echo  AstroEngine : %ASTRO_REMOTE%
echo  PyJHora     : %PYJHORA_REMOTE%
echo.
echo  Teammate setup commands:
echo    git clone %ASTRO_REMOTE%
echo    git clone %PYJHORA_REMOTE%
echo    cd AstroEngine
echo    copy .env.example .env
echo    pip install -r requirements.txt
echo    pip install -e ..\PyJHora\src
echo    build_frontend.bat
echo    python start.py
echo ============================================================
pause
