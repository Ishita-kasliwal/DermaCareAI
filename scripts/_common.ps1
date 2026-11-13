# Shared helpers for start/stop/status/restart.
# Safety rules:
#   * Only ever acts on the process whose PID is recorded in run\app.pid.
#   * Before acting, verifies that process's executable is THIS project's
#     .venv python AND that its start time matches (guards against PID reuse).
#   * Never stops processes by name; never touches other projects or MySQL.

$ErrorActionPreference = 'Stop'
$Root    = Split-Path -Parent $PSScriptRoot
$VenvPy  = Join-Path $Root '.venv\Scripts\python.exe'
$RunDir  = Join-Path $Root 'run'
$PidFile = Join-Path $RunDir 'app.pid'
$OutLog  = Join-Path $RunDir 'app.out.log'
$ErrLog  = Join-Path $RunDir 'app.err.log'

function Get-EnvValue([string]$Name, [string]$Default) {
    # Reads a single key from this project's .env (no global env vars are set).
    $envFile = Join-Path $Root '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match "^\s*$Name\s*=\s*(.*)\s*$") { return $Matches[1].Trim('"', "'") }
        }
    }
    return $Default
}

$AppHost = Get-EnvValue 'APP_HOST' '127.0.0.1'
$AppPort = [int](Get-EnvValue 'APP_PORT' '8010')
$HealthUrl = "http://${AppHost}:${AppPort}/health"

function Get-AppProcess {
    # Returns the verified app process, or $null (cleans up stale PID files).
    if (-not (Test-Path $PidFile)) { return $null }
    try { $info = Get-Content $PidFile -Raw | ConvertFrom-Json } catch { Remove-Item $PidFile -Force; return $null }
    $proc = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
    $ok = $false
    if ($proc) {
        try {
            $sameExe   = ($proc.Path -ieq $VenvPy)
            $sameStart = ($proc.StartTime.ToUniversalTime().ToString('o') -eq $info.started)
            $ok = $sameExe -and $sameStart
        } catch { $ok = $false }
    }
    if (-not $ok) { Remove-Item $PidFile -Force; return $null }
    return $proc
}

function Get-PortOwner([int]$Port) {
    # Ignore PID 0 ("Idle"): Windows briefly keeps a listener entry for a socket whose process
    # has already exited. That is not another program using the port.
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 } | Select-Object -First 1
    if ($c) { return Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue }
    return $null
}

function Test-Health {
    try { $r = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3; return ($r.status -eq 'ok') } catch { return $false }
}
