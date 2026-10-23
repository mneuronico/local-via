<#
.SYNOPSIS
  Shared helpers for the install scripts (dot-source it; it does nothing on its own):
  - an install log in logs\ that keeps the full output, including that of git, pip and npm;
  - running external programs with their output logged and their exit code checked;
  - a prerequisite check that lists everything missing at once, with how to fix each item.
#>

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Starts logs\<name>-<date>.log, unless an outer install script already did (install-worker runs install-wangp).
# Returns $true when this call owns the log and must close it with Stop-InstallLog.
# $Secrets are blanked out of the file when it is closed: the transcript header repeats the command line, which
# includes them when the script is started with powershell -File.
function Start-InstallLog([string]$Name, [string[]]$Secrets = @()) {
    if ($global:LocalViaInstallLog) { return $false }
    $dir = Join-Path $script:RepoRoot "logs"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $global:LocalViaInstallLog = Join-Path $dir ("{0}-{1}.log" -f $Name, (Get-Date -Format "yyyyMMdd-HHmmss"))
    $global:LocalViaLogSecrets = @($Secrets | Where-Object { $_ })
    Start-Transcript -LiteralPath $global:LocalViaInstallLog | Out-Null
    # Unbuffered, UTF-8 Python output so pip and WanGP's setup show up in order and with accents intact.
    $env:PYTHONUNBUFFERED = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    Write-Host "Local Via: $Name"
    Write-Host "Equipo: $env:COMPUTERNAME | Usuario: $env:USERNAME | Windows: $($os.Caption) $($os.Version) | PowerShell: $($PSVersionTable.PSVersion)"
    Write-Host "Repositorio: $script:RepoRoot | Commit: $(Get-RepoCommit)"
    Write-Host "Log: $global:LocalViaInstallLog"
    Write-Host ""
    return $true
}

# Closes the log if this script owns it and it is still open. Install scripts call it from catch with the error
# record, so the error itself is logged (PowerShell prints it only after the transcript is closed), and again
# from finally, which also covers Ctrl+C.
function Stop-InstallLog([bool]$Owned, $ErrorRecord = $null) {
    if (-not $Owned -or -not $global:LocalViaInstallLog) { return }
    $log = $global:LocalViaInstallLog
    if ($ErrorRecord) {
        Write-Host ""
        Write-Host "ERROR: $($ErrorRecord.Exception.Message)" -ForegroundColor Red
        # Where it failed, unless it is one of the scripts' own messages, which already say what went wrong.
        if ($ErrorRecord.FullyQualifiedErrorId -ne $ErrorRecord.Exception.Message) { Write-Host $ErrorRecord.InvocationInfo.PositionMessage -ForegroundColor DarkGray }
        Write-Host "La instalación NO terminó. El detalle completo quedó en:" -ForegroundColor Red
        Write-Host "  $log" -ForegroundColor Red
        Write-Host "Si pedís ayuda, mandá ese archivo (no contiene tokens ni contraseñas)." -ForegroundColor Red
    } else {
        Write-Host "Log: $log" -ForegroundColor DarkGray
    }
    Stop-Transcript | Out-Null
    $global:LocalViaInstallLog = $null
    if ($global:LocalViaLogSecrets) {
        $text = [IO.File]::ReadAllText($log)
        foreach ($secret in $global:LocalViaLogSecrets) { $text = $text.Replace($secret, "<oculto>") }
        [IO.File]::WriteAllText($log, $text, (New-Object Text.UTF8Encoding $true))
    }
}

function Get-RepoCommit {
    # Windows PowerShell turns a native program's stderr into an error even with 2>$null; with "Stop" that aborts.
    $ErrorActionPreference = "Continue"
    if (-not (Test-Path -LiteralPath (Join-Path $script:RepoRoot ".git"))) { return "(sin .git)" }
    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { return "(git no instalado)" }
    $commit = & git.exe -C $script:RepoRoot rev-parse --short HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { return "(desconocido)" }
    return $commit
}

# Runs an external program and fails with $Description if it exits with an error. Its output goes through
# PowerShell so the transcript keeps it (Windows PowerShell does not log console programs otherwise), and its
# stderr is only logged, not turned into an error: git and pip write progress there.
# With -Quiet the output is returned instead, and printed only if the program fails.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$Quiet,
        [int[]]$SuccessCodes = @(0)
    )
    Write-Host "> $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
    $ErrorActionPreference = "Continue"
    $previousEncoding = [Console]::OutputEncoding
    try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
    try {
        $lines = & $FilePath @Arguments 2>&1 | ForEach-Object {
            $line = "$_"
            if ($Quiet) { $line } else { Write-Host $line }
        }
        $code = $LASTEXITCODE
    } finally {
        try { [Console]::OutputEncoding = $previousEncoding } catch { }
    }
    if ($SuccessCodes -notcontains $code) {
        if ($Quiet) { $lines | ForEach-Object { Write-Host $_ } }
        throw "$Description falló (código de salida $code). El detalle está arriba y en el log."
    }
    if ($Quiet) { return $lines }
}

function Test-IsAdmin {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# The first real python.exe on PATH; the WindowsApps stub only opens the Microsoft Store.
function Find-Python {
    return Get-Command python.exe -All -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike "*\WindowsApps\*" } | Select-Object -First 1 -ExpandProperty Source
}

function Test-Url([string]$Url) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $Url -Method Head -UseBasicParsing -TimeoutSec 15 | Out-Null
        return $true
    } catch {
        # Any HTTP answer, even an error status, means the site is reachable.
        return [bool]$_.Exception.Response
    }
}

function Test-TcpPort([string]$HostName, [int]$Port) {
    $client = New-Object Net.Sockets.TcpClient
    try { return $client.ConnectAsync($HostName, $Port).Wait(5000) } catch { return $false } finally { $client.Dispose() }
}

<#
  Checks what an install needs on this PC and prints one line per item:
    [OK]     present
    [AVISO]  works, but worth fixing
    [FALTA]  the install cannot continue; the line says how to fix it
  Throws if anything is missing (unless -NoThrow), so the install stops before changing anything.
  Roles: wangp (WanGP and the models), worker (agent; with -Backend wangp it includes wangp), hub.
#>
function Assert-Prerequisites {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("wangp", "worker", "hub")][string]$Role,
        [string]$Backend = "wangp",
        [bool]$NeedAdmin = $false,
        [string]$ModelRoot = "",
        [string]$HubUrl = "",
        [string]$CaFile = "",
        [switch]$NoThrow
    )
    # The checks run git, nvidia-smi, python and node; a message of theirs on stderr must not abort the check.
    $ErrorActionPreference = "Continue"
    $results = New-Object System.Collections.Generic.List[object]
    function Add-Result([string]$Status, [string]$Item, [string]$Detail) {
        $results.Add([pscustomobject]@{ Status = $Status; Item = $Item; Detail = $Detail })
    }
    $needsWangp = $Role -eq "wangp" -or ($Role -eq "worker" -and $Backend -eq "wangp")

    Write-Host "== Revisando requisitos ($Role)" -ForegroundColor Cyan

    if ([Environment]::Is64BitOperatingSystem) { Add-Result "OK" "Windows 64 bits" "" }
    else { Add-Result "FALTA" "Windows 64 bits" "Local Via necesita Windows 10/11 de 64 bits." }

    if ($NeedAdmin) {
        if (Test-IsAdmin) { Add-Result "OK" "Administrador" "" }
        else { Add-Result "FALTA" "Administrador" "Cerrá esta consola y abrila con clic derecho > 'Ejecutar como administrador'." }
    }

    if (Test-Path -LiteralPath (Join-Path $script:RepoRoot ".git")) { Add-Result "OK" "Repositorio" $script:RepoRoot }
    else { Add-Result "AVISO" "Repositorio" "La carpeta no es un clon de git (¿se bajó como ZIP?). Para actualizar con 'git pull' conviene clonarla: git clone https://github.com/mneuronico/local-via.git" }
    if ($script:RepoRoot -match "\s") {
        Add-Result "AVISO" "Ruta del repositorio" "La ruta tiene espacios ($script:RepoRoot). Algunas herramientas fallan con eso; conviene una ruta corta como D:\local-via."
    }

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) { Add-Result "OK" "Git" ((& git.exe --version) -replace "^git version ", "") }
    elseif ($needsWangp) { Add-Result "FALTA" "Git" "Instalalo con:  conda install -y git   (o desde https://git-scm.com y después cerrá y volvé a abrir la consola)." }
    else { Add-Result "AVISO" "Git" "Sin Git no se puede actualizar con 'git pull'. Instalalo con:  conda install -y git   (o desde https://git-scm.com)." }

    $python = Find-Python
    if ($needsWangp) {
        # WanGP's installer creates its environment with conda, which it calls through cmd.exe.
        $conda = Get-Command conda.exe, conda.bat -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conda) { Add-Result "OK" "Conda" $conda.Source }
        else { Add-Result "FALTA" "Conda" "Instalá Anaconda o Miniconda (https://www.anaconda.com/download) y ejecutá este script desde 'Anaconda PowerShell Prompt' abierto como administrador." }
        if ($python) { Add-Result "OK" "Python (para el instalador de WanGP)" $python }
        else { Add-Result "FALTA" "Python (para el instalador de WanGP)" "No hay python.exe en el PATH. Ejecutá el script desde 'Anaconda PowerShell Prompt'." }

        $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
        $gpu = if ($smi) { & $smi.Source "--query-gpu=name,driver_version,memory.total" "--format=csv,noheader" 2>$null }
        if ($gpu -and $LASTEXITCODE -eq 0) { Add-Result "OK" "GPU NVIDIA" (@($gpu) -join "; ") }
        else { Add-Result "FALTA" "GPU NVIDIA" "nvidia-smi no responde. Instalá o actualizá el driver de NVIDIA (https://www.nvidia.com/Download/index.aspx). No hace falta el CUDA Toolkit: WanGP trae su propio PyTorch con CUDA." }

        $modelDir = if ($ModelRoot) { $ModelRoot } else { $script:RepoRoot }
        $drive = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($modelDir))
        try {
            $freeGb = [math]::Floor((New-Object IO.DriveInfo $drive).AvailableFreeSpace / 1GB)
            if ($freeGb -lt 40) { Add-Result "FALTA" "Espacio en $drive" "$freeGb GB libres. WanGP solo ocupa unos 20 GB y cada modelo entre 5 y 40 GB más." }
            elseif ($freeGb -lt 250) { Add-Result "AVISO" "Espacio en $drive" "$freeGb GB libres. Alcanza para algunos modelos; el catálogo completo ocupa unos 240 GB." }
            else { Add-Result "OK" "Espacio en $drive" "$freeGb GB libres" }
        } catch { Add-Result "AVISO" "Espacio en $drive" "No se pudo medir el espacio libre." }

        $longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
        if ($longPaths -ne 1 -and $script:RepoRoot.Length -gt 20) {
            Add-Result "AVISO" "Rutas largas" "Windows tiene desactivadas las rutas largas y el repositorio está en una ruta larga; algunas dependencias de Python pueden fallar al instalarse. Conviene una ruta corta como D:\local-via."
        }

        foreach ($url in @("https://github.com", "https://pypi.org", "https://huggingface.co")) {
            if (Test-Url $url) { Add-Result "OK" "Acceso a $url" "" }
            else { Add-Result "FALTA" "Acceso a $url" "No hay conexión. Revisá la red o el proxy de la universidad." }
        }
    }

    if ($Role -eq "hub" -or ($Role -eq "worker" -and $Backend -ne "wangp")) {
        if (-not $python) {
            Add-Result "FALTA" "Python 3.11 o 3.12" "Instalalo desde https://www.python.org/downloads/ marcando 'Add python.exe to PATH', o ejecutá el script desde 'Anaconda PowerShell Prompt'."
        } else {
            $version = & $python -c "import sys; print('%d.%d' % sys.version_info[:2])"
            if ([version]$version -lt [version]"3.11") { Add-Result "FALTA" "Python 3.11 o 3.12" "El python.exe del PATH es $version ($python). Instalá 3.11 o 3.12." }
            elseif ([version]$version -gt [version]"3.12") { Add-Result "AVISO" "Python 3.11 o 3.12" "El python.exe del PATH es $version ($python); el hub se probó con 3.11 y 3.12. Creá un entorno con la versión probada y volvé a ejecutar el script desde ahí:  conda create -y -n localvia-hub python=3.12 nodejs   y después   conda activate localvia-hub" }
            else { Add-Result "OK" "Python $version" $python }
        }
    }

    if ($Role -eq "hub") {
        if (Test-Path -LiteralPath (Join-Path $script:RepoRoot "out\index.html")) { Add-Result "OK" "Interfaz web" "ya compilada (out\)" }
        elseif (Get-Command npm.cmd -ErrorAction SilentlyContinue) { Add-Result "OK" "Node.js" ((& node.exe --version) -join "") }
        else { Add-Result "FALTA" "Node.js" "Hace falta para compilar la interfaz web. Instalalo en el entorno de conda activo con:  conda install -y nodejs   (o desde https://nodejs.org, o copiá la carpeta out\ ya compilada desde otra PC)." }
        if (-not (Test-Url "https://pypi.org")) { Add-Result "FALTA" "Acceso a https://pypi.org" "No hay conexión. Revisá la red o el proxy de la universidad." }

        # The hub's firewall rule covers Domain and Private networks only: on a Public network nobody could connect.
        $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
        $public = @($profiles | Where-Object { "$($_.NetworkCategory)" -eq "Public" })
        if (-not $profiles.Count) { Add-Result "AVISO" "Tipo de red" "No se pudo leer el tipo de red de Windows. Revisalo con:  Get-NetConnectionProfile" }
        elseif ($public.Count) {
            $names = ($public | ForEach-Object { "$($_.InterfaceAlias) ($($_.Name))" }) -join ", "
            Add-Result "AVISO" "Tipo de red" "La red $names está como Pública. La regla de firewall del hub solo vale en redes de Dominio o Privadas, así que ni los estudiantes ni las otras PCs podrían conectarse. Pedile a TI que la clasifique como Dominio o Privada (o, como Administrador:  Set-NetConnectionProfile -InterfaceAlias '$($public[0].InterfaceAlias)' -NetworkCategory Private)."
        } else {
            Add-Result "OK" "Tipo de red" (($profiles | ForEach-Object { "$($_.InterfaceAlias): $($_.NetworkCategory)" }) -join "; ")
        }

        # The address and subnet to pass to install-hub.ps1 (-HostNames, -LabSubnet), so nobody has to work them out.
        foreach ($p in $profiles) {
            $ip = Get-NetIPAddress -InterfaceIndex $p.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { "$($_.PrefixOrigin)" -ne "WellKnown" -and $_.PrefixLength -lt 32 } | Select-Object -First 1
            if (-not $ip) { continue }
            $bytes = ([Net.IPAddress]$ip.IPAddress).GetAddressBytes()
            $mask = [uint32]([math]::Pow(2, 32) - [math]::Pow(2, 32 - $ip.PrefixLength))
            $maskBytes = [BitConverter]::GetBytes($mask); [Array]::Reverse($maskBytes)
            $network = (0..3 | ForEach-Object { $bytes[$_] -band $maskBytes[$_] }) -join "."
            $dhcp = if ("$($ip.PrefixOrigin)" -eq "Dhcp") { " Es una IP por DHCP: pedile a TI que sea fija o una reserva para esta PC." } else { "" }
            Add-Result "OK" "Dirección de esta PC" "$env:COMPUTERNAME, $($ip.IPAddress) en la subred $network/$($ip.PrefixLength) ($($p.InterfaceAlias)). Para install-hub.ps1:  -HostNames `"$env:COMPUTERNAME,$($ip.IPAddress)`" -LabSubnet `"$network/$($ip.PrefixLength)`".$dhcp"
        }
    }

    if ($Role -eq "worker") {
        if ($CaFile) {
            if (Test-Path -LiteralPath $CaFile) { Add-Result "OK" "Certificado del hub" $CaFile }
            else { Add-Result "FALTA" "Certificado del hub" "No existe $CaFile. Copiá hub\certs\hub.crt desde la PC del hub (nunca hub.key)." }
        }
        if ($HubUrl) {
            try {
                $uri = [Uri]$HubUrl
                if (Test-TcpPort $uri.Host $uri.Port) { Add-Result "OK" "Conexión al hub" "$($uri.Host):$($uri.Port)" }
                else { Add-Result "AVISO" "Conexión al hub" "No responde $($uri.Host):$($uri.Port). Se puede instalar igual, pero el agente no va a conectarse hasta que el hub esté instalado y el firewall lo permita." }
            } catch { Add-Result "FALTA" "URL del hub" "'$HubUrl' no es una URL válida (ejemplo: https://aula-pc-01:8443)." }
        }
    }

    $colors = @{ OK = "Green"; AVISO = "Yellow"; FALTA = "Red" }
    foreach ($r in $results) {
        $line = "  [{0}]{1} {2}" -f $r.Status, (" " * (5 - $r.Status.Length)), $r.Item
        if ($r.Detail) { $line += ": $($r.Detail)" }
        Write-Host $line -ForegroundColor $colors[$r.Status]
    }
    $missing = @($results | Where-Object Status -eq "FALTA")
    if ($missing.Count) {
        $message = "Faltan $($missing.Count) requisito(s), marcados con [FALTA] arriba. Resolvelos y volvé a ejecutar el script."
        if (-not $NoThrow) { throw $message }
        Write-Host $message -ForegroundColor Red
    } else {
        Write-Host "Requisitos completos." -ForegroundColor Green
    }
    Write-Host ""
    if ($NoThrow) { return $missing.Count }
}
