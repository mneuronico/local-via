<#
.SYNOPSIS
  Installs WanGP (the generation engine, with its own conda environment) in .runtime\Wan2GP.

.DESCRIPTION
  Run it from "Anaconda PowerShell Prompt". It checks first that Git, conda, the NVIDIA driver, disk space and
  Internet access are there, and stops listing whatever is missing. Everything is logged in logs\.
  Models are not downloaded here: each one is downloaded the first time it is used (or with smoke_wangp_model.py).

.EXAMPLE
  .\scripts\install-wangp.ps1
#>
param([string]$ModelRoot = "", [switch]$SkipChecks)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$projectRoot = $RepoRoot
$wangpRoot = Join-Path $projectRoot ".runtime\Wan2GP"
if (-not $ModelRoot) {
    $ModelRoot = if (Test-Path -LiteralPath "N:\") { "N:\local-via-models\ckpts" } else { Join-Path $projectRoot ".runtime\model-cache\ckpts" }
}

$ownsLog = Start-InstallLog "install-wangp"
try {
    if (-not $SkipChecks) { Assert-Prerequisites -Role wangp -ModelRoot $ModelRoot }

    Write-Host "== 1/4 Código de WanGP" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath (Join-Path $wangpRoot ".git"))) {
        New-Item -ItemType Directory -Force -Path (Split-Path $wangpRoot) | Out-Null
        Invoke-Native "La descarga de WanGP (git clone)" "git.exe" @("clone", "--depth", "1", "https://github.com/deepbeepmeep/Wan2GP.git", $wangpRoot)
    } else {
        Write-Host "Ya estaba descargado en $wangpRoot"
    }

    Write-Host "== 2/4 Entorno de Python de WanGP (la primera vez tarda 15 a 30 minutos)" -ForegroundColor Cyan
    $wangpPython = Join-Path $wangpRoot "env_conda\python.exe"
    if (-not (Test-Path -LiteralPath $wangpPython)) {
        Push-Location $wangpRoot
        try { Invoke-Native "El instalador de WanGP (setup.py)" (Find-Python) @("setup.py", "install", "--auto", "--env", "conda") }
        finally { Pop-Location }
    } else {
        Write-Host "Ya estaba creado: $wangpPython"
    }
    if (-not (Test-Path -LiteralPath $wangpPython)) { throw "El instalador de WanGP terminó pero no creó $wangpPython. Revisá su salida arriba." }
    Invoke-Native "La instalación de hf_transfer" $wangpPython @("-m", "pip", "install", "--disable-pip-version-check", "hf_transfer")

    Write-Host "== 3/4 Carpeta de modelos" -ForegroundColor Cyan
    $checkpointPath = Join-Path $wangpRoot "ckpts"
    New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null
    if (-not (Test-Path -LiteralPath $checkpointPath)) {
        New-Item -ItemType Junction -Path $checkpointPath -Target (Resolve-Path $ModelRoot).Path | Out-Null
    }
    Write-Host "$checkpointPath -> $ModelRoot"

    Write-Host "== 4/4 Verificación" -ForegroundColor Cyan
    Push-Location $projectRoot
    try { $output = Invoke-Native "La verificación de WanGP (verify_wangp.py)" $wangpPython @("scripts\verify_wangp.py") -Quiet }
    finally { Pop-Location }
    $text = $output -join "`n"
    $report = $text.Substring($text.IndexOf("{")) | ConvertFrom-Json
    $known = @($report.found).Count
    $downloaded = @($report.availability.PSObject.Properties | Where-Object { $_.Value.available }).Count
    if (-not $known) { throw "WanGP arrancó pero no reconoce ningún modelo del catálogo. Revisá el log." }
    Write-Host "WanGP funciona: reconoce $known modelos del catálogo; $downloaded ya están descargados."
    Write-Host "WanGP listo." -ForegroundColor Green
    if (-not $downloaded) {
        Write-Host "Para descargar un modelo y hacer una generación de prueba (usa la GPU de verdad):"
        Write-Host "  .runtime\Wan2GP\env_conda\python.exe scripts\smoke_wangp_model.py z_image"
    }
} catch {
    Stop-InstallLog $ownsLog $_
    # The error is already on screen and in the log; an outer install script reports it itself.
    if ($ownsLog) { exit 1 }
    throw
} finally {
    Stop-InstallLog $ownsLog
}
