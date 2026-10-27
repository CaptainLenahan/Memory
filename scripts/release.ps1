<#
  Ship a new version of Memory. Bumps backend\version.py, commits, tags vX.Y.Z and pushes. GitHub Actions then runs
  the tests, builds Memory-Setup-X.Y.Z.exe and publishes it as a GitHub Release.

    powershell -ExecutionPolicy Bypass -File scripts\release.ps1               # 1.0.0 -> 1.0.1 (fixes)
    powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -Bump minor   # 1.0.1 -> 1.1.0 (new features)
    powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -Bump major   # 1.1.0 -> 2.0.0 (big changes)
    powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -Version 1.4.0

  Commit your changes first; this refuses to run with uncommitted work or failing tests.
#>
param([ValidateSet('patch', 'minor', 'major')][string]$Bump = 'patch', [string]$Version)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (git status --porcelain) { throw 'You have uncommitted changes. Commit them (or stash them) first.' }
if ((git branch --show-current) -ne 'main') { throw 'Release from the main branch.' }
git pull --ff-only --quiet
if ($LASTEXITCODE) { throw 'Could not update from GitHub (git pull).' }

python -m pytest tests -q
if ($LASTEXITCODE) { throw 'Tests failed, so nothing was released.' }

$file = 'backend\version.py'
$text = Get-Content $file -Raw
$current = [regex]::Match($text, '__version__ = "(\d+)\.(\d+)\.(\d+)"')
$repo = [regex]::Match($text, 'REPO = "([^"]+)"').Groups[1].Value
if (-not $Version) {
  $maj, $min, $pat = [int]$current.Groups[1].Value, [int]$current.Groups[2].Value, [int]$current.Groups[3].Value
  $Version = switch ($Bump) { 'major' { "$($maj + 1).0.0" } 'minor' { "$maj.$($min + 1).0" } default { "$maj.$min.$($pat + 1)" } }
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must look like 1.2.3 (got $Version)." }
if (git tag --list "v$Version") { throw "v$Version already exists." }

Set-Content $file ($text -replace '__version__ = "[^"]+"', "__version__ = `"$Version`"") -NoNewline
if (git status --porcelain) { git commit --quiet -am "Release v$Version" }  # unchanged when re-releasing the current number
git tag -a "v$Version" -m "Memory $Version"
git push --quiet origin main "v$Version"
if ($LASTEXITCODE) { throw 'Push failed. The release commit and tag exist locally; run: git push origin main v' + $Version }

"Released v$Version."
"GitHub is building the installer now (about 5 minutes): https://github.com/$repo/actions"
"It will appear here when done:                        https://github.com/$repo/releases"
