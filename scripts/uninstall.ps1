<#
.SYNOPSIS
  Removes the Local Via scheduled tasks and firewall rule from this computer (run as Administrator).
  Data (data\hub, generated files) and the repository folder are left in place.
#>
$ErrorActionPreference = "Continue"
foreach ($name in @("Local Via Hub", "Local Via Worker")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Tarea eliminada: $name"
    }
}
Get-NetFirewallRule -DisplayName "Local Via Hub" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "Listo. Para borrar también los datos, eliminá la carpeta data\ manualmente."
