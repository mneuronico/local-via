<#
.SYNOPSIS
  Lists what this PC still needs before installing Local Via, without changing anything.

.DESCRIPTION
  One line per item: [OK], [AVISO] (works, but worth fixing) or [FALTA] (the install would fail), with how to fix it.
  The install scripts run the same check on their own; this one is for looking before installing.
  The result is also saved in logs\, to send it if you ask for help.

.EXAMPLE
  .\scripts\check-prereqs.ps1                 # lab PC with GPU (WanGP and agent)
.EXAMPLE
  .\scripts\check-prereqs.ps1 -Role hub       # the PC that will be the hub
#>
param([ValidateSet("wangp", "worker", "hub")][string]$Role = "wangp")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$ownsLog = Start-InstallLog "check-$Role"
try {
    $missing = Assert-Prerequisites -Role $Role -NeedAdmin ($Role -ne "wangp") -NoThrow
} catch {
    Stop-InstallLog $ownsLog $_
    # The error is already on screen and in the log; an outer install script reports it itself.
    if ($ownsLog) { exit 1 }
    throw
} finally {
    Stop-InstallLog $ownsLog
}
if ($missing) { exit 1 }
