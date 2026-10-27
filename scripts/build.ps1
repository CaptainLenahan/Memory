<#
  Build Memory for Windows. Produces, in dist\:
    Memory\                          the app (Memory.exe with Python and every library bundled)
    Memory-<version>-portable.zip    that folder zipped (unzip and run Memory.exe --open)
    Memory-Setup-<version>.exe       the installer (needs Inno Setup 6; skipped if it isn't installed)

    powershell -ExecutionPolicy Bypass -File scripts\build.ps1

  Needs Python 3.12+. PyInstaller goes into a private .build-venv, so your normal Python is untouched.
  Inno Setup: winget install JRSoftware.InnoSetup   (GitHub Actions installs it automatically)
  The version comes from backend\version.py.
#>
param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (python -c "import sys; sys.path.insert(0, '.'); from backend.version import __version__; print(__version__)").Trim()
"Building Memory $version"

$venv = Join-Path $root '.build-venv'
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
$py = "$venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt pyinstaller
if ($LASTEXITCODE) { throw 'pip install failed' }

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
# absolute paths: with --specpath, PyInstaller resolves relative ones against the spec folder
& $py -m PyInstaller --noconfirm --clean --windowed --name Memory --icon "$root\frontend\icon.ico" `
  --add-data "$root\frontend;frontend" --collect-submodules uvicorn --collect-data certifi `
  --exclude-module pytest --exclude-module tkinter --specpath build "$root\launcher.pyw"
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
Copy-Item README.md, THIRD_PARTY_NOTICES.md dist\Memory\

$zip = "dist\Memory-$version-portable.zip"
Compress-Archive -Path dist\Memory\* -DestinationPath $zip -Force
"Portable build: $zip"

if ($SkipInstaller) { return }
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { Write-Warning 'Inno Setup 6 not found, so no installer was built (winget install JRSoftware.InnoSetup).'; return }
& $iscc /Qp "/DAppVersion=$version" packaging\memory.iss
if ($LASTEXITCODE) { throw 'Inno Setup failed' }
"Installer: dist\Memory-Setup-$version.exe"
