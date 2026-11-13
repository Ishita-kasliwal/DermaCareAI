# Packs the committed project code (no data, models, .env or secrets) into a zip for Google Colab.
#   .\scripts\make_colab_bundle.ps1   ->  run\dermacare_colab_bundle.zip
# Only COMMITTED files are included (git archive), so commit your changes first.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root 'run\dermacare_colab_bundle.zip'
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
Push-Location $Root
try {
    if (git status --porcelain) { Write-Warning "You have uncommitted changes; they will NOT be in the bundle." }
    & git archive --format=zip -o $Out HEAD
    if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
    Write-Host ("Created {0} ({1:N1} MB) from commit {2}" -f $Out, ((Get-Item $Out).Length / 1MB), (git rev-parse --short HEAD))
    Write-Host "Next: open notebooks\train_on_colab.ipynb in Google Colab and upload this zip when asked."
} finally { Pop-Location }
