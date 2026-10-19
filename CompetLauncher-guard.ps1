# CompetLauncher-guard.ps1
# ---------------------------------------------------------------------------
# Runs just before CompetLauncher starts (second action of the logon task).
#
# Why: the task uses MultipleInstances=Parallel so a leftover instance cannot
# block a new logon, but that means every failed start can leave an orphan
# launcher behind.  An orphan is a CompetLauncher.exe with no Compet.exe child
# -- it holds a gamepad bridge open and does nothing else.
#
# This script kills only those orphans.  A launcher that owns a live
# Compet.exe is never touched.
# ---------------------------------------------------------------------------

$ErrorActionPreference = "SilentlyContinue"

$exe = "CompetLauncher"
foreach ($p in (Get-CimInstance Win32_Process -Filter "Name='CompetLauncher.exe'")) {
    $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.ProcessId)")
    if ($kids.Count -eq 0) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
