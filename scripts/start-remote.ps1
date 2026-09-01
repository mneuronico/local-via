$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workerUp = Get-NetTCPConnection -LocalPort 9000 -State Listen -ErrorAction SilentlyContinue

if (-not $workerUp) {
    & (Join-Path $PSScriptRoot "start-local.ps1")
}

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:9000/health" | Out-Null
        break
    } catch {
        if ($attempt -eq 59) { throw }
        Start-Sleep -Seconds 1
    }
}

$tunnelUp = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'tunnel\s+run' }
if (-not $tunnelUp) {
    & (Join-Path $PSScriptRoot "start-tunnel.ps1")
}
