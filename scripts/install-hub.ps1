<#
.SYNOPSIS
  Installs the Local Via hub on the lab PC that will coordinate the room (run once, as Administrator).

.DESCRIPTION
  - Creates .venv with the hub dependencies and builds the web interface (out/).
  - Writes hub/.env (mode, port, TLS, allowed networks).
  - Generates a self-signed TLS certificate unless one issued by the university is given.
  - Creates the first administration account.
  - Opens the hub port in Windows Firewall only for the given networks.
  - Registers the "Local Via Hub" scheduled task so the hub starts with Windows.

.EXAMPLE
  # Option A: students reach the hub on the campus network or through the university VPN.
  .\scripts\install-hub.ps1 -Mode lan -HostNames "aula-pc-01,10.20.30.11" -LabSubnet "10.20.30.0/24" -StudentNetworks "10.0.0.0/8" -AdminUser profe

.EXAMPLE
  # Option B: students arrive through Cloudflare Tunnel; only the lab subnet can reach the port directly.
  .\scripts\install-hub.ps1 -Mode tunnel -HostNames "aula-pc-01,10.20.30.11" -LabSubnet "10.20.30.0/24" -AdminUser profe
#>
param(
    [ValidateSet("lan", "tunnel")][string]$Mode = "lan",
    [int]$Port = 8443,
    [Parameter(Mandatory = $true)][string]$HostNames,
    [Parameter(Mandatory = $true)][string]$LabSubnet,
    [string]$StudentNetworks = "",
    [string]$AdminNetworks = "",
    [string]$AdminUser = "admin",
    [string]$TlsCertFile = "",
    [string]$TlsKeyFile = "",
    [string]$DataDir = "",
    [int]$RetentionDays = 14,
    [switch]$SkipAdmin,
    [switch]$SkipFirewall,
    [switch]$SkipTask
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
# The current account by SID and full name: a computer named like the user makes bare names ambiguous.
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$mySid = $me.User.Value
Set-Location $root

function Assert-Admin {
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Ejecutá este script en una consola de PowerShell abierta como Administrador." }
}
if (-not ($SkipFirewall -and $SkipTask)) { Assert-Admin }

Write-Host "== 1/6 Entorno de Python del hub" -ForegroundColor Cyan
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "No se encontró Python 3.11 o 3.12 (python.exe) en el PATH." }
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $python -m venv .venv }
& .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r hub\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias del hub." }

Write-Host "== 2/6 Interfaz web" -ForegroundColor Cyan
if (-not (Test-Path "out\index.html")) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "Falta out\index.html y no hay Node.js para compilarla. Instalá Node.js LTS o copiá la carpeta out\ ya compilada." }
    & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw "npm ci falló." }
    & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "npm run build falló." }
}

Write-Host "== 3/6 Certificado TLS" -ForegroundColor Cyan
if ($TlsCertFile -and $TlsKeyFile) {
    $cert = (Resolve-Path $TlsCertFile).Path; $key = (Resolve-Path $TlsKeyFile).Path
    Write-Host "Usando el certificado provisto: $cert"
} else {
    if (Test-Path "hub\certs\hub.key") { icacls (Join-Path $root "hub\certs\hub.key") /reset | Out-Null }
    & .venv\Scripts\python.exe -m hub.cli make-cert --hosts $HostNames --out hub\certs
    $cert = Join-Path $root "hub\certs\hub.crt"; $key = Join-Path $root "hub\certs\hub.key"
    # Only the account running the hub (and Administrators/SYSTEM) may read the private key.
    icacls $key /inheritance:r /grant:r "*${mySid}:R" "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
}

Write-Host "== 4/6 Configuración (hub\.env)" -ForegroundColor Cyan
if (-not $DataDir) { $DataDir = Join-Path $root "data\hub" }
if (-not $AdminNetworks) { $AdminNetworks = $LabSubnet }
$envLines = @(
    "LOCALVIA_HUB_MODE=$Mode",
    "LOCALVIA_HUB_HOST=0.0.0.0",
    "LOCALVIA_HUB_PORT=$Port",
    "LOCALVIA_HUB_TLS_CERT_FILE=$cert",
    "LOCALVIA_HUB_TLS_KEY_FILE=$key",
    "LOCALVIA_HUB_DATA_DIR=$DataDir",
    "LOCALVIA_HUB_UI_DIR=$(Join-Path $root 'out')",
    "LOCALVIA_HUB_WORKER_NETWORKS=$LabSubnet",
    "LOCALVIA_HUB_ADMIN_NETWORKS=$AdminNetworks",
    "LOCALVIA_HUB_RETENTION_DAYS=$RetentionDays"
)
Set-Content -LiteralPath "hub\.env" -Value $envLines -Encoding ASCII

Write-Host "== 5/6 Cuenta de administración" -ForegroundColor Cyan
if (-not $SkipAdmin) {
    & .venv\Scripts\python.exe -m hub.cli create-admin $AdminUser
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la cuenta de administración." }
}

Write-Host "== 6/6 Firewall e inicio automático" -ForegroundColor Cyan
if (-not $SkipFirewall) {
    $remote = @($LabSubnet)
    if ($Mode -eq "lan") {
        if (-not $StudentNetworks) { throw "En modo lan indicá -StudentNetworks (subred del campus y/o del pool de la VPN)." }
        $remote += $StudentNetworks.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }
    Get-NetFirewallRule -DisplayName "Local Via Hub" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName "Local Via Hub" -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress $remote -Action Allow -Profile Domain,Private | Out-Null
    Write-Host "Puerto $Port abierto solo para: $($remote -join ', ')"
}
if (-not $SkipTask) {
    $action = New-ScheduledTaskAction -Execute (Join-Path $root ".venv\Scripts\python.exe") -Argument "-m hub" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId $me.Name -LogonType S4U -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName "Local Via Hub" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "Local Via Hub"
    Write-Host "Tarea 'Local Via Hub' registrada e iniciada."
}

$first = $HostNames.Split(",")[0].Trim()
Write-Host ""
Write-Host "Hub listo en https://${first}:$Port" -ForegroundColor Green
Write-Host "Siguiente paso: registrar cada computadora del laboratorio:"
Write-Host "  .venv\Scripts\python.exe -m hub.cli add-worker aula-pc-01"
Write-Host "y copiar hub\certs\hub.crt a cada computadora (no copiar hub.key)."
