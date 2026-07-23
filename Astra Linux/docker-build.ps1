# Build Astra Linux/OPC_UA_Gateway using Docker (Debian inside container).
# Requires Docker Desktop. Run from project root or this folder.
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..')
$OutDir = Join-Path $ScriptDir 'OPC_UA_Gateway'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found. Install Docker Desktop or run Install-WSL-And-Build.ps1 as Administrator."
}

Write-Host "=== Docker build for Astra Linux bundle ===" -ForegroundColor Cyan
Set-Location $ProjectRoot

docker build -f "Astra Linux/Dockerfile" -t opcua-gateway-linux-build .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Path $OutDir | Out-Null

$cid = docker create opcua-gateway-linux-build
try {
    docker cp "${cid}:/src/Astra Linux/OPC_UA_Gateway/." $OutDir
} finally {
    docker rm $cid | Out-Null
}

Write-Host "Done: $OutDir" -ForegroundColor Green
