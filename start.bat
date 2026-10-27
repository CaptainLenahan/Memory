@echo off
rem Run Memory from source: installs the Python requirements if needed, starts the server and opens it.
setlocal
cd /d "%~dp0"
python -c "import fastapi, uvicorn, anthropic, msal, multipart, dotenv" 2>nul || (
  echo Installing requirements...
  python -m pip install -r requirements.txt || goto :error
)
start "" pythonw launcher.pyw --open
goto :eof
:error
echo Failed to install requirements.
pause
