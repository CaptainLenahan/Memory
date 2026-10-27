<#
  Run the Memory server automatically when you sign in to Windows, and keep it running.

    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1           # install
    powershell -ExecutionPolicy Bypass -File scripts\startup.ps1 -Remove   # uninstall

  Installs (all per-user, no admin rights needed):
    Task Scheduler  "Memory"   starts the server silently 20 s after you sign in, then checks every 5 minutes and
                               starts it again if it has stopped (the launcher exits at once if it's already running)
    Start menu      "Memory"   opens Memory in your browser (starting the server if needed)
  If your organisation blocks creating scheduled tasks, it falls back to a Startup-folder shortcut instead.
#>
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$taskName = 'Memory'
$startupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory (background).lnk'
$menuLnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Memory.lnk'

if ($Remove) {
  if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; "Removed scheduled task '$taskName'" }
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

$launcher = "`"$root\launcher.pyw`""
$scheduled = $false
try {
  $action = New-ScheduledTaskAction -Execute $pythonw -Argument $launcher -WorkingDirectory $root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $trigger.Delay = 'PT20S'  # let sign-in settle (network, profile) first
  $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition
  # also start checking right away (not only after the next sign-in)
  $heal = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
  $trigger = @($trigger, $heal)
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'Starts the Memory server at sign-in and restarts it if it stops.' -Force | Out-Null
  "Scheduled task '$taskName': starts Memory at sign-in and checks every 5 minutes"
  $scheduled = $true
} catch {
  "Couldn't create a scheduled task ($($_.Exception.Message)); using a Startup-folder shortcut instead."
}

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
if ($scheduled) {
  if (Test-Path $startupLnk) { Remove-Item $startupLnk; "Removed the old Startup-folder shortcut (the scheduled task replaces it)" }
} else {
  New-Shortcut $startupLnk $launcher 'Start the Memory server in the background'
}
New-Shortcut $menuLnk "$launcher --open" 'Open Memory'
