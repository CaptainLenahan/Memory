<#
  Run Memory automatically when you sign in to Windows.

    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1           # install
    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1 -Remove   # uninstall

  Installs two per-user shortcuts (no admin rights needed):
    Startup folder  "Memory (background)"  starts the server silently at sign-in
    Start menu      "Memory"               opens Memory in your browser (starting the server if needed)
#>
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$startupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory (background).lnk'
$menuLnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Memory.lnk'

if ($Remove) {
  foreach ($l in $startupLnk, $menuLnk) { if (Test-Path $l) { Remove-Item $l; "Removed $l" } }
  return
}

# Resolve the real interpreter (not the WindowsApps alias, which breaks if app execution aliases are turned off).
$python = (& (Get-Command python -ErrorAction Stop).Source -c "import sys; print(sys.executable)").Trim()
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }

# Make sure the dependencies are installed before relying on a windowless start.
& $python -c "import fastapi, uvicorn, anthropic, msal, multipart, dotenv" 2>$null
if ($LASTEXITCODE -ne 0) { & $python -m pip install -r (Join-Path $root 'requirements.txt') }

$shell = New-Object -ComObject WScript.Shell
function New-Shortcut($path, $arguments, $description) {
  $s = $shell.CreateShortcut($path)
  $s.TargetPath = $pythonw
  $s.Arguments = $arguments
  $s.WorkingDirectory = $root
  $s.IconLocation = (Join-Path $root 'frontend\icon.ico') + ',0'
  $s.Description = $description
  $s.Save()
  "Created $path"
}
New-Shortcut $startupLnk "`"$root\launcher.pyw`"" 'Start the Memory server in the background'
New-Shortcut $menuLnk "`"$root\launcher.pyw`" --open" 'Open Memory'
