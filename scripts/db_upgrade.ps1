# Applies database migrations (Alembic) with the schema account, then seeds the skin conditions.
# The environment variable below is set for THIS PowerShell process only and removed afterwards.
# Note: Alembic writes normal progress logs to stderr, so success is judged by exit codes only.
$Root = Split-Path -Parent $PSScriptRoot
$Flask = Join-Path $Root '.venv\Scripts\flask.exe'
Push-Location $Root
try {
    $env:SKINAI_DB_ROLE = 'migrate'
    & cmd.exe /c "`"$Flask`" --app wsgi db upgrade 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "migration failed (exit $LASTEXITCODE)" }
    & cmd.exe /c "`"$Flask`" --app wsgi seed-classes 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "seeding failed (exit $LASTEXITCODE)" }
    Write-Host "Database schema is up to date."
} finally {
    Remove-Item Env:\SKINAI_DB_ROLE -ErrorAction SilentlyContinue
    Pop-Location
}
