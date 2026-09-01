param([string]$ModelRoot = "")

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$wangpRoot = Join-Path $projectRoot ".runtime\Wan2GP"
if (-not (Test-Path -LiteralPath (Join-Path $wangpRoot ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $wangpRoot) | Out-Null
    git clone --depth 1 https://github.com/deepbeepmeep/Wan2GP.git $wangpRoot
}
$wangpPython = Join-Path $wangpRoot "env_conda\python.exe"
if (-not (Test-Path -LiteralPath $wangpPython)) {
    Push-Location $wangpRoot
    try { python setup.py install --auto --env conda }
    finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath $wangpPython)) { throw "WanGP no creó env_conda correctamente." }

& $wangpPython -m pip install hf_transfer

if (-not $ModelRoot) {
    $ModelRoot = if (Test-Path -LiteralPath "N:\") { "N:\local-via-models\ckpts" } else { Join-Path $projectRoot ".runtime\model-cache\ckpts" }
}
$checkpointPath = Join-Path $wangpRoot "ckpts"
New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null
if (-not (Test-Path -LiteralPath $checkpointPath)) {
    New-Item -ItemType Junction -Path $checkpointPath -Target (Resolve-Path $ModelRoot).Path | Out-Null
}

Push-Location $projectRoot
try { & $wangpPython scripts\verify_wangp.py | Out-Null }
finally { Pop-Location }
Write-Host "WanGP listo. Checkpoints: $checkpointPath -> $ModelRoot"
