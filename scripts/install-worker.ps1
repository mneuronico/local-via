<#
.SYNOPSIS
  Installs the Local Via agent on a lab PC (run as Administrator on each of the GPU computers, including the hub PC).

.DESCRIPTION
  The agent only makes outbound HTTPS connections to the hub; it opens no port on this computer.
  - Installs WanGP (unless -Backend mock) and, optionally, copies the model checkpoints from a network share or disk.
  - Writes worker\.env with the hub URL, this computer's token and the hub certificate to trust.
  - Registers the "Local Via Worker" scheduled task so the agent starts with Windows.

.EXAMPLE
  .\scripts\install-worker.ps1 -HubUrl https://aula-pc-01:8443 -Token <token de add-worker> -CaFile D:\hub.crt -ModelSource \\aula-pc-01\local-via-ckpts
#>
param(
    [Parameter(Mandatory = $true)][string]$HubUrl,
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$CaFile = "",
    [ValidateSet("wangp", "mock")][string]$Backend = "wangp",
    [string]$ModelSource = "",
    [string]$ModelRoot = "",
    [string]$DataDir = "",
    [int]$MaxGpuTempC = 85,
    [switch]$SkipTask
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
# The current account by SID and full name: a computer named like the user makes bare names ambiguous.
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$mySid = $me.User.Value
Set-Location $root
if (-not $HubUrl.StartsWith("https://")) { throw "La URL del hub debe ser https://" }

if ($Backend -eq "wangp") {
    Write-Host "== WanGP" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "install-wangp.ps1") -ModelRoot $ModelRoot
    $python = Join-Path $root ".runtime\Wan2GP\env_conda\python.exe"
    if ($ModelSource) {
        Write-Host "== Copiando modelos desde $ModelSource (puede tardar; son cientos de GB)" -ForegroundColor Cyan
        $target = (Get-Item (Join-Path $root ".runtime\Wan2GP\ckpts")).Target
        if (-not $target) { $target = Join-Path $root ".runtime\Wan2GP\ckpts" }
        robocopy $ModelSource $target /E /Z /MT:8 /R:2 /W:5 /NP /NFL /NDL | Out-Host
        if ($LASTEXITCODE -ge 8) { throw "robocopy informó errores al copiar los modelos." }
    }
} else {
    if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
    & .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r worker\requirements.txt
    $python = Join-Path $root ".venv\Scripts\python.exe"
}
& $python -m pip install --disable-pip-version-check -q -r worker\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias del agente." }

Write-Host "== Configuración (worker\.env)" -ForegroundColor Cyan
if (-not $DataDir) { $DataDir = Join-Path $root "data\worker" }
$lines = @(
    "LOCALVIA_WORKER_HUB_URL=$HubUrl",
    "LOCALVIA_WORKER_TOKEN=$Token",
    "LOCALVIA_WORKER_BACKEND=$Backend",
    "LOCALVIA_WORKER_DATA_DIR=$DataDir",
    "LOCALVIA_WORKER_WANGP_ROOT=$(Join-Path $root '.runtime\Wan2GP')",
    "LOCALVIA_WORKER_MAX_GPU_TEMP_C=$MaxGpuTempC"
)
if ($CaFile) {
    New-Item -ItemType Directory -Force -Path "worker\certs" | Out-Null
    Copy-Item -LiteralPath $CaFile -Destination "worker\certs\hub.crt" -Force
    $lines += "LOCALVIA_WORKER_CA_FILE=$(Join-Path $root 'worker\certs\hub.crt')"
}
if (Test-Path "worker\.env") { icacls (Join-Path $root "worker\.env") /reset | Out-Null }
Set-Content -LiteralPath "worker\.env" -Value $lines -Encoding ASCII
# The token grants access to students' inputs: only this account and Administrators may read it.
icacls (Join-Path $root "worker\.env") /inheritance:r /grant:r "*${mySid}:R" "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null

if (-not $SkipTask) {
    $action = New-ScheduledTaskAction -Execute $python -Argument "-m worker" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId $me.Name -LogonType S4U -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName "Local Via Worker" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "Local Via Worker"
    Write-Host "Tarea 'Local Via Worker' registrada e iniciada."
}
Write-Host "Agente configurado. En unos segundos la computadora aparece como conectada en Administración > Sala." -ForegroundColor Green
