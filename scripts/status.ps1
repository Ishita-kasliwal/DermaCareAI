# STATUS: reports process, port and health. Read-only.
. (Join-Path $PSScriptRoot '_common.ps1')

$proc = Get-AppProcess
if ($proc) {
    $healthy = Test-Health
    $uptime = (Get-Date) - $proc.StartTime
    Write-Host "Status : RUNNING"
    Write-Host "PID    : $($proc.Id)"
    Write-Host "URL    : http://${AppHost}:${AppPort}"
    Write-Host "Health : $(if ($healthy) { 'OK' } else { 'NOT RESPONDING' })"
    Write-Host ("Uptime : {0:hh\:mm\:ss}" -f $uptime)
    if (-not $healthy) { exit 2 }
    exit 0
}

Write-Host "Status : STOPPED"
$owner = Get-PortOwner $AppPort
if ($owner) { Write-Host "Note   : port $AppPort is in use by another process ($($owner.ProcessName), PID $($owner.Id))." }
exit 1
