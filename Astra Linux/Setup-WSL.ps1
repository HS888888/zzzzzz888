#Requires -RunAsAdministrator
# Enable WSL2 components and build OPC UA Gateway inside Ubuntu.
# If this script reports BIOS virtualization is disabled, enable Intel VT-x / AMD-V in BIOS first.

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AsciiRoot = Join-Path $env:USERPROFILE 'Desktop\opcua_gateway_wsl'
$LogFile = Join-Path $PSScriptRoot 'setup-wsl.log'

function Write-Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

Write-Log '=== OPC UA Gateway: WSL setup + Linux build ==='

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if ($cpu.VirtualizationFirmwareEnabled -eq $false) {
    Write-Log 'ERROR: CPU virtualization is disabled in BIOS/UEFI.'
    Write-Log 'Enable Intel VT-x or AMD-V, save BIOS, reboot, then run this script again.'
    exit 2
}

Write-Log 'Enabling Windows features for WSL2...'
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null

Write-Log 'Installing Ubuntu for WSL...'
wsl --install Ubuntu --no-launch
wsl --set-default-version 2

Write-Log 'Copying project to ASCII path...'
if (Test-Path $AsciiRoot) { Remove-Item -Recurse -Force $AsciiRoot }
New-Item -ItemType Directory -Path $AsciiRoot | Out-Null
robocopy $ProjectRoot $AsciiRoot /E /XD build dist production .git "Astra Linux\.build-venv" "Astra Linux\.source-venv" "Astra Linux\.pyinstaller-build" "Astra Linux\.pyinstaller-dist" "Astra Linux\OPC_UA_Gateway" "Astra Linux\release" /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null

$drive = $AsciiRoot.Substring(0, 1).ToLower()
$rest = $AsciiRoot.Substring(2).Replace('\', '/')
$winPath = "/mnt/$drive$rest"
$wslProject = '/home/opcua/build'

Write-Log 'Building inside Ubuntu (15-30 min)...'
$cmd = @"
set -euo pipefail
mkdir -p '$wslProject'
cp -a '$winPath'/.' '$wslProject'/
cd '$wslProject/Astra Linux'
chmod +x preflight.sh install_system_deps.sh validate_source.sh build.sh package_release.sh packaging/Запуск.sh
./preflight.sh
sudo ./install_system_deps.sh
./validate_source.sh
./build.sh
./package_release.sh
"@

wsl -d Ubuntu -- bash -lc $cmd

Write-Log 'Copying build back to project...'
$Built = Join-Path $ProjectRoot 'Astra Linux\OPC_UA_Gateway'
$Release = Join-Path $ProjectRoot 'Astra Linux\release'
$SourceApp = Join-Path $AsciiRoot 'Astra Linux\OPC_UA_Gateway'
$SourceRelease = Join-Path $AsciiRoot 'Astra Linux\release'

if (-not (Test-Path $SourceApp)) {
    throw "Build output not found: $SourceApp"
}

if (Test-Path $Built) { Remove-Item -Recurse -Force $Built }
robocopy $SourceApp $Built /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null

if (Test-Path $SourceRelease) {
    if (Test-Path $Release) { Remove-Item -Recurse -Force $Release }
    robocopy $SourceRelease $Release /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
}

Write-Log "Done: $Built"
Write-Log "Archive: $Release"
