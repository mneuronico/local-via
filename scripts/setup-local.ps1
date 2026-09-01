$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    npm install
    if (-not (Test-Path -LiteralPath "worker\.venv\Scripts\python.exe")) { python -m venv worker\.venv }
    worker\.venv\Scripts\python.exe -m pip install -r worker\requirements.txt
    npm run build
    worker\.venv\Scripts\python.exe -m pytest worker\tests -q
} finally { Pop-Location }

