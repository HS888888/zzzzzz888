#Requires -RunAsAdministrator
# One-time setup: enable WSL, install Ubuntu, build Astra Linux/OPC_UA_Gateway.
# Right-click PowerShell -> Run as Administrator, then:
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   & "C:\Users\HS\Desktop\Роман романтик\Astra Linux\Install-WSL-And-Build.ps1"

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AsciiRoot = Join-Path $env:USERPROFILE 'Desktop\opcua_gateway_wsl'
$WslProject = '/home/opcua/build'

Write-Host "=== WSL + Astra Linux build ===" -ForegroundColor Cyan

Write-Host "[1/5] Enabling WSL..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null

Write-Host "[2/5] Installing Ubuntu (WSL)..."
wsl --install Ubuntu --no-launch 2>$null
if ($LASTEXITCODE -ne 0) {
    wsl --install -d Ubuntu --no-launch
}

Write-Host "[3/5] Copying project to ASCII path: $AsciiRoot"
if (Test-Path $AsciiRoot) { Remove-Item -Recurse -Force $AsciiRoot }
New-Item -ItemType Directory -Path $AsciiRoot | Out-Null
robocopy $ProjectRoot $AsciiRoot /E /XD build dist production .git "Astra Linux\.build-venv" "Astra Linux\OPC_UA_Gateway" /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null

Write-Host "[4/5] Building inside WSL (first run may take 15-30 min)..."
$drive = $AsciiRoot.Substring(0, 1).ToLower()
$rest = $AsciiRoot.Substring(2).Replace('\', '/')
$winPath = "/mnt/$drive$rest"
$cmd = @"
set -euo pipefail
mkdir -p '$WslProject'
cp -a '$winPath'/.' '$WslProject'/
cd '$WslProject/Astra Linux'
chmod +x build.sh packaging/Запуск.sh
sudo ./install_system_deps.sh
./build.sh
"@

wsl -d Ubuntu -- bash -lc $cmd

Write-Host "[5/5] Copying result back to project..."
$Built = Join-Path $ProjectRoot 'Astra Linux\OPC_UA_Gateway'
$Source = Join-Path $AsciiRoot 'Astra Linux\OPC_UA_Gateway'
if (-not (Test-Path $Source)) {
    throw "Build output not found: $Source"
}
if (Test-Path $Built) { Remove-Item -Recurse -Force $Built }
robocopy $Source $Built /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null

Write-Host "Done: $Built" -ForegroundColor Green
