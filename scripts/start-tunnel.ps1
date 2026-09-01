$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$binary = Join-Path $projectRoot ".runtime\bin\cloudflared.exe"
$tokenPath = Join-Path $projectRoot ".runtime\cloudflared.token"
$logDir = Join-Path $projectRoot "data\logs"
$pidDir = Join-Path $projectRoot "data\pids"
$logPath = Join-Path $logDir "tunnel.err.log"

if (-not (Test-Path -LiteralPath $binary)) {
    throw "Falta cloudflared. Ejecutá scripts/install-cloudflared.ps1."
}
if (-not (Test-Path -LiteralPath $tokenPath)) {
    throw "Falta la credencial del túnel permanente en .runtime/cloudflared.token."
}

Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:9000/health" | Out-Null
New-Item -ItemType Directory -Force -Path $logDir, $pidDir | Out-Null
$process = Start-Process -FilePath $binary -ArgumentList @("tunnel", "run", "--token-file", $tokenPath) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "tunnel.out.log") -RedirectStandardError $logPath -PassThru
Set-Content -LiteralPath (Join-Path $pidDir "tunnel.pid") -Value $process.Id

Start-Sleep -Seconds 2
if ($process.HasExited) { throw "El túnel no pudo iniciarse. Revisá $logPath" }
Write-Host "Worker HTTPS: https://localvia-worker.mneuronico.com"
