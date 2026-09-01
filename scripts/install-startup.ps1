$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Local Via.lnk"
$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$runner = Join-Path $projectRoot "scripts\start-remote.ps1"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Inicia Local Via y su túnel permanente"
$shortcut.Save()

Write-Host "Inicio automático instalado: $shortcutPath"
