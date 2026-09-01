$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$targetDir = Join-Path $projectRoot ".runtime\bin"
$target = Join-Path $targetDir "cloudflared.exe"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Invoke-WebRequest -UseBasicParsing "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $target
& $target --version
