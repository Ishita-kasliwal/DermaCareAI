# Creates the project-local virtual environment (.venv) with Python 3.12
# and installs dependencies. Touches nothing outside this project folder.
#   .\scripts\setup_venv.ps1          # create if missing, install/upgrade deps
#   .\scripts\setup_venv.ps1 -Clean   # delete .venv and rebuild from scratch
param([switch]$Clean)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Py   = Join-Path $Venv 'Scripts\python.exe'

if ($Clean -and (Test-Path $Venv)) {
    Write-Host "Removing existing .venv..."
    Remove-Item -Recurse -Force $Venv
}
if (-not (Test-Path $Py)) {
    Write-Host "Creating .venv with Python 3.12..."
    py -3.12 -m venv $Venv
}

& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Root 'requirements-dev.txt')
& $Py -m pip freeze | Set-Content -Path (Join-Path $Root 'requirements.lock.txt') -Encoding ascii

Write-Host "Done. Interpreter: $Py"
& $Py --version
