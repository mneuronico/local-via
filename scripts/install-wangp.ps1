<#
.SYNOPSIS
  Installs WanGP (the generation engine, with its own conda environment) in .runtime\Wan2GP.

.DESCRIPTION
  Run it from "Anaconda PowerShell Prompt". It checks first that Git, conda, the NVIDIA driver, disk space and
  Internet access are there, and stops listing whatever is missing. Everything is logged in logs\.
  Models are not downloaded here: each one is downloaded the first time it is used (or with smoke_wangp_model.py).
  WanGP is pinned to the version the catalog and the agent were tested with (-WanGPCommit changes it). If a previous
  run stopped halfway, running the script again rebuilds the environment.

.EXAMPLE
  .\scripts\install-wangp.ps1
#>
param(
    [string]$ModelRoot = "",
    # The WanGP version measured in docs/MODEL_COMPATIBILITY.md and MODEL_BENCHMARKS.md.
    [string]$WanGPCommit = "89a77e37d4e7f66634f5227558254b8095314ad1",
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$projectRoot = $RepoRoot
$wangpRoot = Join-Path $projectRoot ".runtime\Wan2GP"
$wangpPython = Join-Path $wangpRoot "env_conda\python.exe"
if (-not $ModelRoot) {
    $ModelRoot = if (Test-Path -LiteralPath "N:\") { "N:\local-via-models\ckpts" } else { Join-Path $projectRoot ".runtime\model-cache\ckpts" }
}

# WanGP's installer registers env_conda in envs.json only after every step succeeded, so a python.exe without that
# entry is an environment left halfway by a failed run.
function Test-WanGPEnvComplete {
    $envsFile = Join-Path $wangpRoot "envs.json"
    if (-not (Test-Path -LiteralPath $wangpPython) -or -not (Test-Path -LiteralPath $envsFile)) { return $false }
    try { return [bool](Get-Content -LiteralPath $envsFile -Raw | ConvertFrom-Json).envs.env_conda } catch { return $false }
}

function Get-WanGPHead {
    $ErrorActionPreference = "Continue"
    $head = & git.exe -C $wangpRoot rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return "$head".Trim()
}

$ownsLog = Start-InstallLog "install-wangp"
try {
    if (-not $SkipChecks) { Assert-Prerequisites -Role wangp -ModelRoot $ModelRoot }
    $complete = Test-WanGPEnvComplete

    Write-Host "== 1/4 Código de WanGP" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath (Join-Path $wangpRoot ".git"))) {
        New-Item -ItemType Directory -Force -Path $wangpRoot | Out-Null
        Invoke-Native "La creación del repositorio de WanGP" "git.exe" @("-C", $wangpRoot, "init", "-q")
        Invoke-Native "La configuración del repositorio de WanGP" "git.exe" @("-C", $wangpRoot, "remote", "add", "origin", "https://github.com/deepbeepmeep/Wan2GP.git")
    }
    $head = Get-WanGPHead
    if ($head -eq $WanGPCommit) {
        Write-Host "WanGP ya está en la versión probada ($($WanGPCommit.Substring(0, 7)))."
    } elseif ($complete) {
        # A working install is left alone; changing its code under an existing environment could break it.
        Write-Host "AVISO: WanGP está en $head y la versión probada es $WanGPCommit. Se deja como está porque ya funciona." -ForegroundColor Yellow
    } else {
        Write-Host "Descargando WanGP en la versión probada ($($WanGPCommit.Substring(0, 7)))..."
        Invoke-Native "La descarga de WanGP (git fetch)" "git.exe" @("-C", $wangpRoot, "fetch", "--depth", "1", "origin", $WanGPCommit)
        Invoke-Native "El cambio a la versión probada de WanGP" "git.exe" @("-C", $wangpRoot, "-c", "advice.detachedHead=false", "checkout", "--force", "FETCH_HEAD")
    }

    Write-Host "== 2/4 Entorno de Python de WanGP (la primera vez tarda 15 a 30 minutos)" -ForegroundColor Cyan
    if ($complete) {
        Write-Host "Ya estaba creado: $wangpPython"
    } else {
        if (Test-Path -LiteralPath $wangpPython) { Write-Host "Hay un entorno a medio instalar de un intento anterior; el instalador de WanGP lo borra y lo crea de nuevo." }
        # WanGP's installer runs pip through "conda run", which goes through a .bat file on Windows: there "%2B" (an
        # encoded "+") in a wheel URL turns into "B" and pip rejects the wheel. GitHub accepts a literal "+", so the
        # URLs are fixed for the install and setup_config.json is restored afterwards.
        $configPath = Join-Path $wangpRoot "setup_config.json"
        $originalConfig = [IO.File]::ReadAllText($configPath)
        if ($originalConfig.Contains("%2B")) {
            [IO.File]::WriteAllText($configPath, $originalConfig.Replace("%2B", "+"), (New-Object Text.UTF8Encoding $false))
            Write-Host "Corregidas las URLs con %2B de setup_config.json para que conda run no las rompa."
        }
        # Every pip call of the installer gets the tested versions as constraints (conda run passes the variable on).
        $env:PIP_CONSTRAINT = Join-Path $PSScriptRoot "wangp-constraints.txt"
        Write-Host "Versiones de dependencias fijadas con $env:PIP_CONSTRAINT"
        Push-Location $wangpRoot
        try { Invoke-Native "El instalador de WanGP (setup.py)" (Find-Python) @("setup.py", "install", "--auto", "--env", "conda") }
        finally {
            Pop-Location
            Remove-Item Env:PIP_CONSTRAINT -ErrorAction SilentlyContinue
            [IO.File]::WriteAllText($configPath, $originalConfig, (New-Object Text.UTF8Encoding $false))
        }
        if (-not (Test-WanGPEnvComplete)) { throw "El instalador de WanGP terminó pero no dejó registrado env_conda. Revisá su salida arriba." }
    }
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
