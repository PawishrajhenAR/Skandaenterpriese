# Run tests with .venv enabled
# Usage: .\run_tests.ps1 [pytest-args...]
# Example: .\run_tests.ps1 -k "TestAuthentication"
# Example: .\run_tests.ps1 --ignore=tests/test_main.py

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

# Activate .venv
$VenvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating .venv..." -ForegroundColor Yellow
    python -m venv .venv
}
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
    Write-Host "Activated .venv" -ForegroundColor Green
} else {
    Write-Host "Warning: .venv\Scripts\Activate.ps1 not found. Using system Python." -ForegroundColor Yellow
}

# Install dependencies (pytest, etc.)
Write-Host "Ensuring dependencies (pip install -r requirements.txt)..." -ForegroundColor Cyan
pip install -q -r requirements.txt

# Run pytest (pass any extra args, e.g. -k "TestAuthentication")
Write-Host "Running pytest tests/ -v --tb=short..." -ForegroundColor Green
python -m pytest tests/ -v --tb=short @args
