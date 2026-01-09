@echo off
echo ===================================================
echo   AI Traveler's Guide - Development Launcher
echo ===================================================

cd /d %~dp0

:: 1. Check if venv exists
if not exist "venv" (
    echo [!] venv not found. Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate
echo [!] Checking dependencies...
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Installing dependencies...
    pip install -r requirements.txt
) else (
    echo [!] Dependencies are up to date.
)

:: 2. Start Flask Server in a new window
echo [*] Starting Flask Server...
start "Flask Server" cmd /k "venv\Scripts\activate & python server.py"

:: 3. Start ngrok in a new window
echo [*] Starting ngrok...
start "ngrok Tunnel" cmd /k "ngrok http 5000"

:: 4. Wait for server to initialize
echo [*] Waiting for services to start...
timeout /t 5 >nul

:: 5. Open Browser
echo [*] Opening Browser...
start http://localhost:5000

echo ===================================================
echo   Startup Complete!
echo   - Close the "Flask Server" window to stop the backend.
echo   - Close the "ngrok Tunnel" window to stop the tunnel.
echo ===================================================
pause
