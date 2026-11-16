<#
  Create (or replace) the token Power Automate uses to push Planner tasks to Memory.

    powershell -ExecutionPolicy Bypass -File scripts\new-sync-token.ps1

  - generates a random 48-character token
  - saves it as MEMORY_PLANNER_SYNC_TOKEN in Memory's .env (%LOCALAPPDATA%\Memory\.env for the installed app,
    or .\.env when running from source with -Source), replacing any previous token
  - copies it to your clipboard (it is not printed), so you can paste it into the flow's HTTP action
  - restarts Memory so the new token takes effect
  Replacing the token immediately locks out anything still using the old one.
#>
param([switch]$Source)
$ErrorActionPreference = 'Stop'

$envFile = if ($Source) { Join-Path (Split-Path -Parent $PSScriptRoot) '.env' } else { Join-Path $env:LOCALAPPDATA 'Memory\.env' }
New-Item -ItemType Directory -Force (Split-Path $envFile) | Out-Null

$bytes = New-Object byte[] 36
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'B').TrimEnd('=')

$lines = @()
if (Test-Path $envFile) { $lines = @(Get-Content $envFile | Where-Object { $_ -notmatch '^\s*MEMORY_PLANNER_SYNC_TOKEN\s*=' }) }
$lines += "MEMORY_PLANNER_SYNC_TOKEN=$token"
Set-Content -Path $envFile -Value $lines -Encoding utf8
Set-Clipboard -Value $token
Remove-Variable token, bytes

"Saved a new sync token to $envFile and copied it to your clipboard."
"Paste it into the Power Automate HTTP action as:  Authorization: Bearer <paste>"

# restart Memory so it reads the new token (the installed app, or a from-source server)
Get-Process -Name 'Memory' -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object CommandLine -like '*launcher.pyw*' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1
if (Get-ScheduledTask -TaskName 'Memory' -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName 'Memory'; 'Memory restarted.' }
else { 'Start Memory again (Start menu > Memory) so it picks up the token.' }
