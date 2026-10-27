<#
  For running Memory from source: start the server automatically when you sign in to Windows, and keep it running.
  (The installer, Memory-Setup.exe, does this for you; you don't need this script if you installed that.)

    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1           # install
    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1 -Remove   # uninstall

  Installs (all per-user, no admin rights needed):
    Task Scheduler  "Memory"   starts the server silently 20 s after you sign in, then checks every 5 minutes and
                               starts it again if it has stopped (falls back to a Startup-folder shortcut if
                               your organisation blocks scheduled tasks)
    Start menu      "Memory"   opens Memory in your browser (starting the server if needed)
#>
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$menuLnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Memory.lnk'

# Resolve the real interpreter (not the WindowsApps alias, which breaks if app execution aliases are turned off).
$python = (& (Get-Command python -ErrorAction Stop).Source -c "import sys; print(sys.executable)").Trim()
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }

if ($Remove) {
  & $python (Join-Path $root 'launcher.pyw') --remove-startup --quiet
  if (Test-Path $menuLnk) { Remove-Item $menuLnk }
  'Removed: Memory no longer starts at sign-in; Start menu shortcut deleted.'
  return
}

# Make sure the dependencies are installed before relying on a windowless start.
& $python -c "import fastapi, uvicorn, anthropic, msal, multipart, dotenv" 2>$null
if ($LASTEXITCODE -ne 0) { & $python -m pip install -r (Join-Path $root 'requirements.txt') }

# Same code the installer uses (backend/startup.py), so there's one implementation of auto-start.
& $python (Join-Path $root 'launcher.pyw') --install-startup --quiet
'Memory will start when you sign in (Task Scheduler task "Memory").'

$s = (New-Object -ComObject WScript.Shell).CreateShortcut($menuLnk)
$s.TargetPath = $pythonw
$s.Arguments = "`"$root\launcher.pyw`" --open"
$s.WorkingDirectory = $root
$s.IconLocation = (Join-Path $root 'frontend\icon.ico') + ',0'
$s.Description = 'Open Memory'
$s.Save()
"Created $menuLnk"
