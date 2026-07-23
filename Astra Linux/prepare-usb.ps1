# Prepare USB folder with LF line endings for Astra Linux.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path $ProjectRoot 'Astra Linux'
$Dest = Read-Host 'Path to USB folder (e.g. E:\Astra Linux)'

if (-not (Test-Path $SourceDir)) { throw "Not found: $SourceDir" }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$files = @(
    'install-opc-gateway.sh',
    'install_runtime_deps.sh',
    'install',
    'ЗАПУСК.txt',
    'Установить-OPC-Gateway.desktop'
)

foreach ($name in $files) {
    $src = Join-Path $SourceDir $name
    if (-not (Test-Path $src)) { continue }
    $text = [IO.File]::ReadAllText($src)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
    $dst = Join-Path $Dest $name
    [IO.File]::WriteAllText($dst, $text, [Text.UTF8Encoding]::new($false))
    Write-Host "OK: $name"
}

Write-Host ""
Write-Host "Copied to: $Dest" -ForegroundColor Green
Write-Host "On Astra open Terminal and run:" -ForegroundColor Cyan
Write-Host '  cd "/media/.../Astra Linux"'
Write-Host '  sudo bash install-opc-gateway.sh'
