# START: launches the app in the background using the project .venv.
. (Join-Path $PSScriptRoot '_common.ps1')

if (-not (Test-Path $VenvPy)) { Write-Error ".venv not found. Run scripts\setup_venv.ps1 first."; exit 1 }

$existing = Get-AppProcess
if ($existing) { Write-Host "Already running (PID $($existing.Id)) at http://${AppHost}:${AppPort}"; exit 0 }

$owner = Get-PortOwner $AppPort
if ($owner) {
    Write-Error "Port $AppPort is already used by another process ($($owner.ProcessName), PID $($owner.Id)). Not touching it. Change APP_PORT in .env."
    exit 1
}

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
$proc = Start-Process -FilePath $VenvPy `
    -ArgumentList '-m', 'waitress', "--host=$AppHost", "--port=$AppPort", '--threads=4', 'wsgi:app' `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog

@{ pid = $proc.Id; started = $proc.StartTime.ToUniversalTime().ToString('o'); port = $AppPort } |
    ConvertTo-Json | Set-Content -Path $PidFile -Encoding ascii

Write-Host -NoNewline "Starting (PID $($proc.Id))"
for ($i = 0; $i -lt 40; $i++) {
    if (Test-Health) { Write-Host "`nRunning at http://${AppHost}:${AppPort}"; exit 0 }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 500; Write-Host -NoNewline '.'
}
Write-Host "`nApp did not become healthy. Last errors:"
if (Test-Path $ErrLog) { Get-Content $ErrLog -Tail 20 }
& (Join-Path $PSScriptRoot 'stop.ps1') | Out-Null
exit 1
