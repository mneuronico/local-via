$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidDir = Join-Path $projectRoot "data\pids"
foreach ($name in @("tunnel", "web", "worker")) {
    $pidFile = Join-Path $pidDir "$name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -Raw -LiteralPath $pidFile)
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) { Stop-Process -Id $processId; Write-Host "Detenido: $name ($processId)" }
        Remove-Item -LiteralPath $pidFile -Force
    }
}
