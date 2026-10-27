@echo off
setlocal
cd /d "%~dp0"
if "%MEMORY_PORT%"=="" set MEMORY_PORT=8765
python -c "import fastapi, uvicorn, anthropic, msal, multipart, dotenv" 2>nul || (
  echo Installing requirements...
  python -m pip install -r requirements.txt || goto :error
)
start "" http://localhost:%MEMORY_PORT%
python -m uvicorn backend.app:app --host 127.0.0.1 --port %MEMORY_PORT%
goto :eof
:error
echo Failed to install requirements.
pause
