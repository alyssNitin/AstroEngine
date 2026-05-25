#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build the React front-end and wire it to FastAPI.

.DESCRIPTION
    Installs npm dependencies and runs `vite build`.
    The compiled output lands in frontend-react/dist/ which FastAPI
    automatically serves when it exists.

.EXAMPLE
    .\scripts\build_frontend.ps1
    .\scripts\build_frontend.ps1 -Dev   # Start Vite dev server instead of building
#>

param(
    [switch]$Dev   # Start the Vite dev server (hot-reload) instead of building
)

$ErrorActionPreference = "Stop"

$Root     = Split-Path $PSScriptRoot -Parent
$FrontDir = Join-Path $Root "frontend-react"

Write-Host "`n🪐 NarayanAstroReader — React Frontend" -ForegroundColor Cyan

# ── Sanity checks ─────────────────────────────────────────────────────────────
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ Node.js not found. Download from https://nodejs.org (LTS recommended)."
    exit 1
}
if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ npm not found. It should come with Node.js."
    exit 1
}

$nodeVer = node --version
$npmVer  = npm --version
Write-Host "   Node $nodeVer  |  npm v$npmVer" -ForegroundColor Gray

# ── Install dependencies ───────────────────────────────────────────────────────
Write-Host "`n📦 Installing dependencies..." -ForegroundColor Yellow
Set-Location $FrontDir
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ npm install failed."
    exit $LASTEXITCODE
}

if ($Dev) {
    # ── Dev server ──────────────────────────────────────────────────────────────
    Write-Host "`n🚀 Starting Vite dev server on http://localhost:5173" -ForegroundColor Green
    Write-Host "   API calls are proxied to http://localhost:8000"      -ForegroundColor Gray
    Write-Host "   Press Ctrl+C to stop.`n"                            -ForegroundColor Gray
    npm run dev
} else {
    # ── Production build ────────────────────────────────────────────────────────
    Write-Host "`n🔨 Building for production..." -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ Build failed. Check errors above."
        exit $LASTEXITCODE
    }

    $DistDir = Join-Path $FrontDir "dist"
    Write-Host "`n✅ Build complete! Output in: $DistDir" -ForegroundColor Green
    Write-Host "   FastAPI will now serve the React app at http://localhost:8000" -ForegroundColor Gray
    Write-Host "   Restart the FastAPI server to pick up the new build:`n" -ForegroundColor Gray
    Write-Host "       python start.py`n" -ForegroundColor White
}
