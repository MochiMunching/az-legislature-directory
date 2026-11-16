# Re-test the two steps that failed in setup.ps1, apply the last fixes, and commit.
# Run from the project folder (the one with index.html):
#   powershell -ExecutionPolicy Bypass -File .\retest.ps1
# Full output goes to retest-log.txt (git-ignored).

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
$log = Join-Path $root "retest-log.txt"
$vpy = Join-Path $root ".venv\Scripts\python.exe"
"retest run $(Get-Date -Format s)" | Set-Content -Encoding utf8 $log

function Run($label, $cmd) {
    Write-Host "=== $label ===" -ForegroundColor Cyan
    "`n=== $label ===`n> $cmd" | Add-Content -Encoding utf8 $log
    # cmd /c captures Python's output and errors, which PowerShell transcripts miss
    $out = & cmd /c "$cmd 2>&1"
    $code = $LASTEXITCODE
    $out | Add-Content -Encoding utf8 $log
    $out | ForEach-Object { Write-Host "  $_" }
    "exit code: $code" | Add-Content -Encoding utf8 $log
    if ($code -eq 0) { Write-Host "  OK" -ForegroundColor Green } else { Write-Host "  FAILED (exit $code)" -ForegroundColor Red }
}

# 1. Keep the log out of git
if (-not (Select-String -Path ".gitignore" -Pattern "^retest-log\.txt" -Quiet)) { Add-Content ".gitignore" "`nretest-log.txt" }

# 2. Workflow: let the site refresh continue if azleg.gov blocks GitHub's servers
$wf = ".github\workflows\refresh-data.yml"
$t = Get-Content $wf -Raw
if ($t -notmatch "continue-on-error") {
    $t = $t -replace "      - name: Roster \(and change log\)\r?\n        run: \|",
        "      # If azleg.gov blocks GitHub's servers, keep going with the last roster`n      # so the rest of the site still refreshes. Check this step's log if it's yellow.`n      - name: Roster (and change log)`n        continue-on-error: true`n        run: |"
    [IO.File]::WriteAllText((Join-Path $root $wf), $t)
    Write-Host "Workflow updated (roster step can no longer stop the whole refresh)"
}

# 3. The two steps that failed, now with full output
Run "Roster scrape" "`"$vpy`" scraper\scrape_roster.py"
Run "Campaign finance test (3 legislators)" "`"$vpy`" scraper\spotlight_finance.py --limit 3"
Run "Site build" "`"$vpy`" scraper\build_site.py"
Run "Private profiles" "`"$vpy`" scraper\build_profiles.py"

# 4. An old clone of az-legislature-directory1 sits inside this folder and got
#    committed as a broken submodule link. Move it next to this folder and untrack it.
$nested = Join-Path $root "az-legislature-directory"
if (Test-Path (Join-Path $nested ".git")) {
    git rm --cached -q az-legislature-directory 2>$null
    $dest = Join-Path (Split-Path $root -Parent) "old-clone-az-legislature-directory1"
    if (-not (Test-Path $dest)) { Move-Item $nested $dest; Write-Host "Moved the old nested clone to $dest" }
    else { Write-Host "Couldn't move the nested clone: $dest already exists" -ForegroundColor Yellow }
}

# 5. Commit (refuses if anything private would be included)
git add -A
$leaked = git diff --cached --name-only | Where-Object { $_ -like "private/*" -or $_ -like ".venv/*" -or $_ -like "*-log.txt" }
if ($leaked) { git reset -q; Write-Host "Private files were about to be committed; nothing committed." -ForegroundColor Red; "LEAK BLOCKED: $leaked" | Add-Content $log }
else {
    git commit -q -m "Fix roster change-log sort, Spotlight committee matching, firewall handling" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "Committed" -ForegroundColor Green } else { Write-Host "Nothing new to commit" }
}
"`n=== git ===" | Add-Content $log
git log --oneline -3 2>&1 | Add-Content $log
git status --short 2>&1 | Add-Content $log
Write-Host "`nDone. Log saved to retest-log.txt"
