<#
.SYNOPSIS
  Installs the Local Via agent on a lab PC (run as Administrator on each of the GPU computers, including the hub PC).

.DESCRIPTION
  The agent only makes outbound HTTPS connections to the hub; it opens no port on this computer.
  - Checks the prerequisites first and stops, listing everything missing, before changing anything.
  - Installs WanGP (unless -Backend mock) and, optionally, copies the model checkpoints from a network share or disk.
  - Writes worker\.env with the hub URL, this computer's token and the hub certificate to trust.
  - Registers the "Local Via Worker" scheduled task so the agent starts with Windows, and shows its first log lines.
  The install output is saved in logs\install-worker-<date>.log and the agent's in logs\worker.log.

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
. (Join-Path $PSScriptRoot "_common.ps1")
$root = $RepoRoot
# The current account by SID and full name: a computer named like the user makes bare names ambiguous.
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$mySid = $me.User.Value
Set-Location $root

$ownsLog = Start-InstallLog "install-worker" -Secrets @($Token)
try {
    if (-not $HubUrl.StartsWith("https://")) { throw "La URL del hub debe empezar con https:// (por ejemplo https://aula-pc-01:8443)." }
    Assert-Prerequisites -Role worker -Backend $Backend -NeedAdmin (-not $SkipTask) -ModelRoot $ModelRoot -HubUrl $HubUrl -CaFile $CaFile

    if ($Backend -eq "wangp") {
        Write-Host "== WanGP" -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "install-wangp.ps1") -ModelRoot $ModelRoot -SkipChecks
        $python = Join-Path $root ".runtime\Wan2GP\env_conda\python.exe"
        if ($ModelSource) {
            Write-Host "== Copiando modelos desde $ModelSource (puede tardar; son cientos de GB)" -ForegroundColor Cyan
            $target = (Get-Item (Join-Path $root ".runtime\Wan2GP\ckpts")).Target
            if (-not $target) { $target = Join-Path $root ".runtime\Wan2GP\ckpts" }
            # robocopy uses exit codes 0-7 for success (files copied, extra files, ...); 8 and up are errors.
            Invoke-Native "La copia de modelos (robocopy)" "robocopy.exe" @($ModelSource, "$target", "/E", "/Z", "/MT:8", "/R:2", "/W:5", "/NP", "/NFL", "/NDL") -SuccessCodes (0..7)
        }
    } else {
        if (-not (Test-Path ".venv\Scripts\python.exe")) { Invoke-Native "La creación de .venv" (Find-Python) @("-m", "venv", ".venv") }
        $python = Join-Path $root ".venv\Scripts\python.exe"
    }
    Write-Host "== Dependencias del agente" -ForegroundColor Cyan
    Invoke-Native "La instalación de las dependencias del agente" $python @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "worker\requirements.txt")

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
    Write-Host "Escrito worker\.env (hub $HubUrl, backend $Backend)."

    if (-not $SkipTask) {
        Write-Host "== Tarea programada" -ForegroundColor Cyan
        $agentLog = Join-Path $root "logs\worker.log"
        $logStart = if (Test-Path -LiteralPath $agentLog) { (Get-Item -LiteralPath $agentLog).Length } else { 0 }
        $action = New-ScheduledTaskAction -Execute $python -Argument "-m worker" -WorkingDirectory $root
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId $me.Name -LogonType S4U -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries
        Register-ScheduledTask -TaskName "Local Via Worker" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Stop-ScheduledTask -TaskName "Local Via Worker" -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName "Local Via Worker"
        Write-Host "Tarea 'Local Via Worker' registrada e iniciada. Esperando sus primeros mensajes..."

        # WanGP takes a while to start; show what the agent logged so far so problems are visible right away.
        $deadline = (Get-Date).AddSeconds(90)
        $news = @()
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 5
            if (Test-Path -LiteralPath $agentLog) {
                $stream = [IO.File]::Open($agentLog, "Open", "Read", "ReadWrite")
                try { [void]$stream.Seek([math]::Min($logStart, $stream.Length), "Begin"); $news = (New-Object IO.StreamReader($stream)).ReadToEnd() -split "`r?`n" | Where-Object { $_ } }
                finally { $stream.Dispose() }
                if ($news -match "Conectado al hub|rechazó|Sin conexión|Error|Traceback") { break }
            }
            if ((Get-ScheduledTask -TaskName "Local Via Worker").State -ne "Running") { break }
        }
        $news | Select-Object -Last 15 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        $task = Get-ScheduledTask -TaskName "Local Via Worker"
        if ($news -match "Conectado al hub") {
            Write-Host "El agente se conectó al hub." -ForegroundColor Green
        } elseif ($task.State -ne "Running") {
            $result = ($task | Get-ScheduledTaskInfo).LastTaskResult
            Write-Host "AVISO: la tarea se detuvo (resultado $result). Revisá logs\worker.log o probá en primer plano:" -ForegroundColor Yellow
            Write-Host "  Stop-ScheduledTask 'Local Via Worker'; & '$python' -m worker" -ForegroundColor Yellow
        } else {
            Write-Host "AVISO: el agente está corriendo pero todavía no confirmó la conexión al hub. Seguí sus mensajes en logs\worker.log." -ForegroundColor Yellow
        }
    }
    Write-Host "Agente configurado. Cuando se conecta, la computadora aparece en Administración > Sala." -ForegroundColor Green
} catch {
    Stop-InstallLog $ownsLog $_
    # The error is already on screen and in the log; an outer install script reports it itself.
    if ($ownsLog) { exit 1 }
    throw
} finally {
    Stop-InstallLog $ownsLog
}
