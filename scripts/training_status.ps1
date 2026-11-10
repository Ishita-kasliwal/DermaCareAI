# Shows training progress: whether it is running, elapsed time, rounds per model and validation scores.
$Root = Split-Path -Parent $PSScriptRoot
$proc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'run_pipeline' } | Select-Object -First 1
if ($proc) {
    $elapsed = (Get-Date) - $proc.CreationDate
    Write-Host ("Training is RUNNING (PID {0}), elapsed {1:hh\:mm\:ss}" -f $proc.ProcessId, $elapsed)
} else {
    Write-Host "Training is NOT running."
}
Push-Location $Root
try { & (Join-Path $Root '.venv\Scripts\python.exe') -m ml.src.training_status } finally { Pop-Location }
