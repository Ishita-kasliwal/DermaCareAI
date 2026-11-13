# PUBLIC STATUS: is the public link up, what is it, and does it answer?
. (Join-Path $PSScriptRoot '_common.ps1')
$Cloudflared = Join-Path $Root 'tools\cloudflared.exe'
$TunnelPid = Join-Path $RunDir 'tunnel.pid'
$UrlFile = Join-Path $RunDir 'public_url.txt'

$running = $false
if (Test-Path $TunnelPid) {
    try {
        $info = Get-Content $TunnelPid -Raw | ConvertFrom-Json
        $p = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
        $running = $p -and $p.Path -ieq $Cloudflared
    } catch { $running = $false }
}
if (-not $running) { Write-Host "Public link: OFF   (start with .\scripts\public_start.ps1)"; exit 1 }

$url = Get-Content $UrlFile -ErrorAction SilentlyContinue
Write-Host "Public link: ON"
Write-Host "URL        : $url"
try {
    $r = Invoke-RestMethod -Uri "$url/health" -TimeoutSec 15
    Write-Host "Reachable  : $(if ($r.status -eq 'ok') { 'YES' } else { 'unexpected reply' })"
} catch {
    Write-Host "Reachable  : not yet (new links can take up to a minute)"
}
& (Join-Path $PSScriptRoot 'status.ps1') | Out-Null
Write-Host "Local app  : $(if (Test-Health) { 'OK' } else { 'NOT RESPONDING' })"
