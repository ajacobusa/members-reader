# =====================================================================
#  QuoteForge / Etsy-Gelato  —  daily High-Availability sync
#
#  Runs from C: (persistent) so it works even when the USB's drive LETTER
#  changed or the USB is unplugged. It:
#    1. finds the project on whatever drive it's on (by marker, not letter)
#    2. pushes code + DB-snapshot + git bundle to GitHub  (backup-all)
#    3. mirrors the whole project (code + data) to C:     (persistent fallback)
#    4. logs everything; exits 0 cleanly if the USB isn't connected
#
#  Deployed + scheduled by:  run.bat ha-install   (admin ha-install)
#  This file is the source of truth, kept in the repo under scripts\.
# =====================================================================
$ErrorActionPreference = 'Continue'

# Relative path of the project from its drive root (stable; the folder name).
$REL    = 'ANOOP PERSONAL HOME\CLAUD\Claud AJ'
$HAROOT = 'C:\QuoteForge-HA'
$MIRROR = Join-Path $HAROOT 'mirror'
$LOGDIR = Join-Path $HAROOT 'logs'
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null
$LOG = Join-Path $LOGDIR 'ha-sync.log'
function Log($m) { "$((Get-Date).ToString('s'))  $m" | Tee-Object -FilePath $LOG -Append | Out-Null }

Log '--- HA sync run start ---'

# 1. Find the project on ANY drive (USB letter is not assumed).
$usb = Get-PSDrive -PSProvider FileSystem |
       Where-Object { Test-Path (Join-Path $_.Root "$REL\quoteforge\config.py") } |
       Select-Object -First 1
if (-not $usb) {
    Log 'Project drive not found (USB unplugged or letter unknown) - skipping this run.'
    exit 0
}
$PROJ = Join-Path $usb.Root $REL
$PY   = Join-Path $PROJ 'python\python.exe'
Log "Found project on drive $($usb.Name): -> $PROJ"

# 2. Code + DB snapshot + git bundle -> GitHub (offsite durability).
#    Uses the drive's own portable python; ignore the system user-site.
$env:PYTHONNOUSERSITE = '1'
if (Test-Path $PY) {
    Push-Location $PROJ
    try {
        # --no-commit: push only COMMITTED work + DB snapshot + bundle. The job must
        # NOT auto-commit in-progress edits to the current branch (that once swept WIP
        # into a chore commit). Uncommitted work is preserved by the C: mirror below.
        & $PY -m quoteforge.admin backup-all --no-commit 2>&1 | Tee-Object -FilePath $LOG -Append | Out-Null
        Log "backup-all (push committed + DB + bundle -> GitHub) exit: $LASTEXITCODE"
    } finally { Pop-Location }
} else {
    Log "WARN portable python missing at $PY - skipped backup-all (code still mirrored below)."
}

# 3. Full mirror -> C: (persistent local fallback incl. data + any WIP).
#    Excludes the reproducible python\ (157 MB) and caches; keeps .git for offline restore.
robocopy "$PROJ" "$MIRROR" /MIR /XD "$PROJ\python" __pycache__ /XF *.pyc `
         /R:1 /W:1 /NFL /NDL /NP /MT:16 2>&1 | Out-Null
$rc = $LASTEXITCODE
Log "mirror -> $MIRROR  robocopy exit: $rc (0-7 = success)"
Log '--- HA sync run complete ---'
exit 0
