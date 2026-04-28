param(
  [switch]$Clean
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting AeroCommand dev stack..." -ForegroundColor Cyan

# Check Docker CLI
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
  Write-Host "Docker CLI not found. Start Docker Desktop and ensure it is on PATH." -ForegroundColor Red
  Write-Host "Expected path: C:\Program Files\Docker\Docker\resources\bin" -ForegroundColor Yellow
  exit 1
}

# Start containers
Push-Location (Split-Path -Parent $PSCommandPath)
Pop-Location

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if ($Clean) {
  Write-Host "Clean rebuild requested: removing existing containers + forcing api-server rebuild..." -ForegroundColor Yellow
  docker compose down
  docker compose build --no-cache api-server
}

docker compose up -d --build

Write-Host "" 
Write-Host "Dev stack started." -ForegroundColor Green
Write-Host "Dashboard: http://localhost:3000" -ForegroundColor Green
Write-Host "API:       http://localhost:8000 (health: /health/ready)" -ForegroundColor Green
Write-Host "EMQX:      http://localhost:18083 (admin / aerocommand_emqx_admin)" -ForegroundColor Green
