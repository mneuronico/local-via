<#
.SYNOPSIS
  Option B: publishes the hub through a Cloudflare Tunnel (outbound only; no inbound port is opened to the Internet).

.DESCRIPTION
  1. In Cloudflare Zero Trust create a tunnel and copy its token.
  2. Add a public hostname (e.g. localvia.example.edu.ar) whose service is https://localhost:<Port>,
     with "No TLS Verify" enabled (the hub uses its own certificate on localhost).
  3. Create a Cloudflare Access application for that hostname (e.g. one-time PIN for institutional e-mails).
  4. Run this script on the hub PC as Administrator; it installs cloudflared as a Windows service.

  The hub must be installed with -Mode tunnel: the administration panel and the worker API are then
  refused for any request that arrives through the tunnel.
#>
param([Parameter(Mandatory = $true)][string]$TunnelToken)

$ErrorActionPreference = "Stop"
$cloudflared = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw "Instalá cloudflared desde https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ y volvé a ejecutar." }
    winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
    $cloudflared = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
    if (-not (Test-Path $cloudflared)) { $cloudflared = (Get-Command cloudflared.exe).Source }
}
& $cloudflared --version
& $cloudflared service install $TunnelToken
Write-Host "Servicio de Cloudflare Tunnel instalado. Verificá en el panel de Zero Trust que el túnel figure como HEALTHY." -ForegroundColor Green
