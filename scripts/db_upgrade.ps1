# Applies database migrations (Alembic) with the schema account, then seeds the 7 categories.
# The environment variable below is set for THIS PowerShell process only and removed afterwards.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Flask = Join-Path $Root '.venv\Scripts\flask.exe'
Push-Location $Root
try {
    $env:SKINAI_DB_ROLE = 'migrate'
    & $Flask --app wsgi db upgrade
    if ($LASTEXITCODE -ne 0) { throw "migration failed" }
    & $Flask --app wsgi seed-classes
    if ($LASTEXITCODE -ne 0) { throw "seeding failed" }
    Write-Host "Database schema is up to date."
} finally {
    Remove-Item Env:\SKINAI_DB_ROLE -ErrorAction SilentlyContinue
    Pop-Location
}
