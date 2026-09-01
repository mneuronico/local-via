param([switch]$Production)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $projectRoot "data\logs"
$pidDir = Join-Path $projectRoot "data\pids"
New-Item -ItemType Directory -Force -Path $logDir, $pidDir | Out-Null

$workerEnv = Join-Path $projectRoot "worker\.env"
$useWanGP = (Test-Path -LiteralPath $workerEnv) -and (Select-String -LiteralPath $workerEnv -Pattern '^LOCAL_VIA_BACKEND=wangp$' -Quiet)
$workerPython = if ($useWanGP) { Join-Path $projectRoot ".runtime\Wan2GP\env_conda\python.exe" } else { Join-Path $projectRoot "worker\.venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $workerPython)) { throw "Falta worker/.venv. Ejecutá scripts/setup-local.ps1." }

$workerArgs = @("-m", "uvicorn", "worker.app.main:app", "--host", "127.0.0.1", "--port", "9000")
$worker = Start-Process -FilePath $workerPython -ArgumentList $workerArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "worker.out.log") -RedirectStandardError (Join-Path $logDir "worker.err.log") -PassThru
Set-Content -LiteralPath (Join-Path $pidDir "worker.pid") -Value $worker.Id

$node = (Get-Command node.exe -ErrorAction Stop).Source
$webArgs = if ($Production) {
    @((Join-Path $projectRoot "node_modules\serve\build\main.js"), (Join-Path $projectRoot "out"), "-l", "3000")
} else {
    @((Join-Path $projectRoot "node_modules\next\dist\bin\next"), "dev")
}
$web = Start-Process -FilePath $node -ArgumentList $webArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "web.out.log") -RedirectStandardError (Join-Path $logDir "web.err.log") -PassThru
Set-Content -LiteralPath (Join-Path $pidDir "web.pid") -Value $web.Id

Write-Host "Local Via iniciado"
Write-Host "Web:    http://localhost:3000"
Write-Host "Worker: http://127.0.0.1:9000/health"
Write-Host "Logs:   $logDir"
