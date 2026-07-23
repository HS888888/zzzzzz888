# Prepare local git repo for GitHub Actions build.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

Write-Host "=== Prepare GitHub upload ===" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git not found. Install from https://git-scm.com/download/win"
}

if (-not (Test-Path '.git')) {
    git init
    git branch -M main
}

git add .
$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit." -ForegroundColor Yellow
} else {
    git -c user.name="HS" -c user.email="hs@local" commit -m "Prepare OPC UA Gateway for GitHub Actions Linux build"
    Write-Host "Committed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Create empty repo on https://github.com/new"
Write-Host "2. Run (replace YOUR_LOGIN and REPO):"
Write-Host '   git remote add origin https://github.com/YOUR_LOGIN/REPO.git'
Write-Host '   git push -u origin main'
Write-Host "3. Open GitHub -> Actions -> Run workflow -> download Artifacts"
Write-Host ""
Write-Host "Full guide: Astra Linux\GITHUB_BUILD.txt"
