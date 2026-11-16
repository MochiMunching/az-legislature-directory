# AZ SBDC legislative directory: one-time setup and first run (Windows PowerShell)
#
# How to run:
#   1. Put this file in the project folder (the one with index.html, data, scraper).
#   2. Right-click the folder in File Explorer > "Open in Terminal", or open PowerShell and cd there.
#   3. Run:   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# It writes a log to setup-log.txt. Send that file back if anything fails.

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
Start-Transcript -Path (Join-Path $root "setup-log.txt") -Force | Out-Null

function Step($n, $text) { Write-Host ""; Write-Host "=== Step $n. $text ===" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  OK   $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  NOTE $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  FAIL $t" -ForegroundColor Red }
$results = [ordered]@{}

Step 1 "Check the project folder"
if (-not (Test-Path "scraper\scrape_roster.py") -or -not (Test-Path "index.html")) {
    Fail "This doesn't look like the project folder. Move setup.ps1 next to index.html and run it again."
    Stop-Transcript | Out-Null; exit 1
}
if (-not (Test-Path ".gitignore")) {
    "private/`n__pycache__/`n.venv/`nsetup-log.txt`n" | Set-Content -Encoding utf8 ".gitignore"
    Warn ".gitignore was missing (hidden files can get lost when unzipping); recreated it"
} elseif (-not (Select-String -Path ".gitignore" -Pattern "^\.venv/" -Quiet)) {
    Add-Content ".gitignore" ".venv/`nsetup-log.txt"
}
Ok "Project folder: $root"

Step 2 "Check Python and Git"
$py = $null
foreach ($c in @("py -3", "python")) {
    try { $v = & cmd /c "$c --version" 2>&1; if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.(\d+)") { if ([int]$Matches[1] -ge 10) { $py = $c; break } } } catch {}
}
if (-not $py) {
    Fail "Python 3.10 or newer not found. Install it from python.org (check 'Add Python to PATH'), then run this script again."
    Stop-Transcript | Out-Null; exit 1
}
Ok "Python: $(& cmd /c "$py --version")"
$hasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($hasGit) { Ok "Git: $(git --version)" } else { Warn "Git not found. Everything else will run; install Git from git-scm.com (or use GitHub Desktop) for the GitHub steps." }

Step 3 "Create the Python environment and install packages"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & cmd /c "$py -m venv .venv" }
$vpy = Join-Path $root ".venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install requests beautifulsoup4 pandas geopandas --quiet
if ($LASTEXITCODE -eq 0) { Ok "Packages installed" } else { Fail "Package install failed; see the messages above" }

function Run($name, [string[]]$scriptArgs) {
    Write-Host "  > python $($scriptArgs -join ' ')"
    & $vpy @scriptArgs
    if ($LASTEXITCODE -eq 0) { $results[$name] = "OK"; Ok $name } else { $results[$name] = "FAILED"; Fail "$name (see output above)" }
}

Step 4 "Live roster test against azleg.gov"
Run "Roster scrape" @("scraper\scrape_roster.py")

Step 5 "Match SBDC centers to districts (and find each office's district)"
Run "District matching (legislative)" @("scraper\match_districts.py")
Run "District matching (congressional)" @("scraper\match_districts.py", "--level", "congressional")

Step 6 "Campaign finance test (3 legislators, Spotlight API)"
Run "Campaign finance test" @("scraper\spotlight_finance.py", "--limit", "3")

Step 7 "Bills and votes (only if an Open States key is set)"
if ($env:OPENSTATES_API_KEY) { Run "Bill discovery" @("scraper\openstates_bills.py", "--discover") }
else { $results["Bill discovery"] = "skipped (no OPENSTATES_API_KEY)"; Warn "Skipped. Get a free key at open.pluralpolicy.com, then:  `$env:OPENSTATES_API_KEY='your-key'; .venv\Scripts\python scraper\openstates_bills.py --discover" }

Step 8 "Draft generator dry run (no API call)"
Run "Brief dry run" @("scraper\generate_briefs.py", "--member", "2308", "--template", "committee_brief", "--dry-run")

Step 9 "Rebuild the site and private profiles"
Run "Source dates" @("scraper\update_sources.py")
Run "Site build" @("scraper\build_site.py")
Run "Private profiles" @("scraper\build_profiles.py")

Step 10 "First Git commit"
if ($hasGit) {
    if (-not (Test-Path ".git")) { git init -q; git branch -M main 2>$null }
    if (-not (git config user.name)) { Warn "Git doesn't know your name yet. Run: git config --global user.name ""Your Name""; git config --global user.email ""you@example.com""; then run this script again." }
    else {
        git add -A
        $leaked = git diff --cached --name-only | Where-Object { $_ -like "private/*" -or $_ -like ".venv/*" }
        if ($leaked) { git reset -q; Fail "Private files were about to be committed; nothing committed. Check .gitignore." }
        else {
            git commit -q -m "AZ SBDC legislative directory: initial setup" 2>$null
            if ($LASTEXITCODE -eq 0) { Ok "Committed" } else { Ok "Nothing new to commit" }
            $results["Git commit"] = "OK"
        }
    }
} else { $results["Git commit"] = "skipped (Git not installed)" }

Write-Host ""; Write-Host "=== Summary ===" -ForegroundColor Cyan
$results.GetEnumerator() | ForEach-Object { "{0,-36} {1}" -f $_.Key, $_.Value }
Write-Host ""
Write-Host "Open private\profiles.html in your browser to see the private profiles."
Write-Host "Next: create an empty PUBLIC repo on github.com, then run:"
Write-Host "  git remote add origin https://github.com/YOUR-USERNAME/az-legislature-directory.git"
Write-Host "  git push -u origin main"
Write-Host "Log saved to setup-log.txt"
Stop-Transcript | Out-Null
