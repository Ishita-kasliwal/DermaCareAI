# STOP: stops ONLY this project's app process (and its child interpreter).
. (Join-Path $PSScriptRoot '_common.ps1')

$proc = Get-AppProcess
if (-not $proc) { Write-Host "Not running."; exit 0 }

# The venv python.exe on Windows is a launcher that spawns the real interpreter
# as a child, so stop the tree rooted at OUR verified PID only.
& taskkill.exe /PID $proc.Id /T /F | Out-Null

for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
# wait (max ~5 s) until no live process listens on the port any more
for ($i = 0; $i -lt 20 -and (Get-PortOwner $AppPort); $i++) { Start-Sleep -Milliseconds 250 }
Write-Host "Stopped (PID $($proc.Id))."
