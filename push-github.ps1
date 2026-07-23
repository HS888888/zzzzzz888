# Push to GitHub (opens browser for login if needed).
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)

$remote = 'https://github.com/HS888888/zzzzzz888.git'
if (-not (git remote get-url origin 2>$null)) {
    git remote add origin $remote
} else {
    git remote set-url origin $remote
}

Write-Host "Pushing to $remote ..." -ForegroundColor Cyan
Write-Host "If a browser opens — sign in to GitHub and allow access." -ForegroundColor Yellow
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done! Open:" -ForegroundColor Green
    Write-Host "https://github.com/HS888888/zzzzzz888/actions"
    Write-Host "Run workflow: Build Astra Linux bundle"
} else {
    Write-Host "Push failed. Check login or use GitHub token." -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to close"
