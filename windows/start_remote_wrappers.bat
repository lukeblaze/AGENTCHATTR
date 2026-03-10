@echo off
REM Start CLI wrappers that connect to a remote hosted server (Render/VM).
REM Usage:
REM   windows\start_remote_wrappers.bat https://agentchattr.onrender.com
REM Optional env vars before running:
REM   set AGENTCHATTR_WRAPPER_KEY=your-shared-secret

setlocal
cd /d "%~dp0.."

if "%~1"=="" (
  echo.
  echo   Usage: windows\start_remote_wrappers.bat ^<server_url^>
  echo   Example: windows\start_remote_wrappers.bat https://agentchattr.onrender.com
  echo.
  exit /b 1
)

set "AGENTCHATTR_SERVER_URL=%~1"

echo.
echo   Remote server: %AGENTCHATTR_SERVER_URL%
if not "%AGENTCHATTR_WRAPPER_KEY%"=="" (
  echo   Wrapper key: configured
) else (
  echo   Wrapper key: not set (required if server enforces AGENTCHATTR_WRAPPER_KEY)
)

if not exist ".venv" (
  python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt >nul 2>nul
)
call .venv\Scripts\activate.bat

start "agentchattr claude wrapper" cmd /c "set AGENTCHATTR_SERVER_URL=%AGENTCHATTR_SERVER_URL%&& set AGENTCHATTR_WRAPPER_KEY=%AGENTCHATTR_WRAPPER_KEY%&& python wrapper.py claude"
start "agentchattr codex wrapper" cmd /c "set AGENTCHATTR_SERVER_URL=%AGENTCHATTR_SERVER_URL%&& set AGENTCHATTR_WRAPPER_KEY=%AGENTCHATTR_WRAPPER_KEY%&& python wrapper.py codex"
start "agentchattr gemini wrapper" cmd /c "set AGENTCHATTR_SERVER_URL=%AGENTCHATTR_SERVER_URL%&& set AGENTCHATTR_WRAPPER_KEY=%AGENTCHATTR_WRAPPER_KEY%&& python wrapper.py gemini"
start "agentchattr kimi wrapper" cmd /c "set AGENTCHATTR_SERVER_URL=%AGENTCHATTR_SERVER_URL%&& set AGENTCHATTR_WRAPPER_KEY=%AGENTCHATTR_WRAPPER_KEY%&& python wrapper.py kimi"

echo.
echo   Started wrapper windows for claude/codex/gemini/kimi.
echo.
endlocal
