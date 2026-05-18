@echo off
REM WhatsApp MCP Launcher for Windows
REM Double-click this file to start the bridge and MCP server
REM No admin rights required — uses portable Go from tools/go/

cd /d "%~dp0"

echo ========================================
echo WhatsApp MCP Launcher
echo ========================================
echo.

REM Set up portable Go (no admin install needed)
set "GOROOT=%USERPROFILE%\tools\go"
set "GO_CMD=%GOROOT%\bin\go.exe"
set "PATH=%GOROOT%\bin;%PATH%"

REM Check for portable Go
if not exist "%GO_CMD%" (
    echo Portable Go not found at %GO_CMD%
    echo Please run: python download_go.py
    pause
    exit /b 1
)

REM Verify Go works
"%GO_CMD%" version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Go binary exists but failed to run.
    echo Try deleting %GOROOT% and re-running download_go.py
    pause
    exit /b 1
)

echo Go found: %GO_CMD%
"%GO_CMD%" version

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download from: https://python.org
    pause
    exit /b 1
)

REM Check if bridge is already running
curl -s http://127.0.0.1:8080/api/health >nul 2>&1
if errorlevel 1 (
    echo.
    echo Starting WhatsApp bridge...
    start "WhatsApp Bridge" cmd /k "cd /d "%~dp0whatsapp-bridge" && set GOROOT=%GOROOT% && set PATH=%GOROOT%\bin;%PATH% && %GO_CMD% run ."
    echo Waiting for bridge to start...
    timeout /t 5 /nobreak >nul
) else (
    echo Bridge is already running.
)

echo.
echo Starting WhatsApp MCP server...
cd /d "%~dp0"
REM Prefer the installed console script; fall back to `python -m whatsapp_mcp`.
where whatsapp-mcp >nul 2>&1
if errorlevel 1 (
    echo Console script `whatsapp-mcp` not found; using `python -m whatsapp_mcp`.
    echo Install editable mode with: pip install -e .
    python -m whatsapp_mcp
) else (
    whatsapp-mcp
)

pause
