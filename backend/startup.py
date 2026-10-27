"""Start Memory when the user signs in to Windows, and keep it running.

A per-user Task Scheduler task starts the server 20 s after sign-in and checks every 5 minutes (the launcher exits at
once if the server is already up). Where an organisation blocks scheduled tasks, it falls back to a Startup-folder
shortcut. No admin rights needed. Used by the installer and by scripts/startup.ps1 (source installs).
"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

from . import paths

TASK = "Memory"

_INSTALL_PS = r"""
$ErrorActionPreference = 'Stop'
$exe = '__EXE__'; $arg = '__ARG__'; $dir = '__DIR__'; $icon = '__ICON__'
$startupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory (background).lnk'
try {
  $action = if ($arg) { New-ScheduledTaskAction -Execute $exe -Argument $arg -WorkingDirectory $dir } else { New-ScheduledTaskAction -Execute $exe -WorkingDirectory $dir }
  $logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $logon.Delay = 'PT20S'
  $logon.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition
  $heal = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName '__TASK__' -Action $action -Trigger @($logon, $heal) -Settings $settings -Principal $principal `
    -Description 'Starts the Memory server at sign-in and restarts it if it stops.' -Force | Out-Null
  if (Test-Path $startupLnk) { Remove-Item $startupLnk }
  'task'
} catch {
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut($startupLnk)
  $s.TargetPath = $exe; $s.Arguments = $arg; $s.WorkingDirectory = $dir; $s.IconLocation = "$icon,0"
  $s.Description = 'Start the Memory server in the background'; $s.Save()
  'shortcut'
}
"""

_REMOVE_PS = r"""
if (Get-ScheduledTask -TaskName '__TASK__' -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName '__TASK__' -Confirm:$false }
$l = Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory (background).lnk'
if (Test-Path $l) { Remove-Item $l }
'removed'
"""


def command() -> tuple[str, str, str]:
    """(program, arguments, working directory) that starts the server with no window."""
    if paths.FROZEN:
        return sys.executable, "", str(paths.INSTALL_DIR)
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return str(pyw if pyw.exists() else sys.executable), f'"{paths.CODE_ROOT / "launcher.pyw"}"', str(paths.CODE_ROOT)


def _powershell(script: str) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
                        base64.b64encode(script.encode("utf-16-le")).decode()],
                       capture_output=True, text=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else (r.stderr.strip() or "failed")


def install() -> str:
    """Register auto-start. Returns 'task' or 'shortcut' (the fallback)."""
    exe, arg, workdir = command()
    q = lambda s: str(s).replace("'", "''")  # noqa: E731  (PowerShell single-quoted string)
    icon = paths.INSTALL_DIR / "Memory.exe" if paths.FROZEN else paths.FRONTEND / "icon.ico"
    script = (_INSTALL_PS.replace("__EXE__", q(exe)).replace("__ARG__", q(arg)).replace("__DIR__", q(workdir))
              .replace("__ICON__", q(icon)).replace("__TASK__", TASK))
    return _powershell(script)


def remove() -> str:
    return _powershell(_REMOVE_PS.replace("__TASK__", TASK))
