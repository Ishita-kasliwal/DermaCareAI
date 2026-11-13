# PUBLIC START: makes the local site reachable through a temporary Cloudflare quick tunnel
# (https://<random>.trycloudflare.com). Free, no account. Works only while this laptop is on.
#  1. restarts the app in PUBLIC_MODE (trust the tunnel's visitor-IP header, Secure cookies)
#  2. starts tools\cloudflared.exe and prints the public HTTPS link (also saved to run\public_url.txt)
. (Join-Path $PSScriptRoot '_common.ps1')
$Cloudflared = Join-Path $Root 'tools\cloudflared.exe'
$TunnelPid = Join-Path $RunDir 'tunnel.pid'
$TunnelLog = Join-Path $RunDir 'tunnel.log'
$UrlFile = Join-Path $RunDir 'public_url.txt'

if (-not (Test-Path $Cloudflared)) { Write-Error "tools\cloudflared.exe not found. See docs/DEPLOYMENT.md."; exit 1 }

function Get-Tunnel {
    if (-not (Test-Path $TunnelPid)) { return $null }
    try { $info = Get-Content $TunnelPid -Raw | ConvertFrom-Json } catch { return $null }
    $p = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
    if ($p -and $p.Path -ieq $Cloudflared -and $p.StartTime.ToUniversalTime().ToString('o') -eq $info.started) { return $p }
    return $null
}

if (Get-Tunnel) {
    Write-Host "Public link is already running: $(Get-Content $UrlFile -ErrorAction SilentlyContinue)"
    exit 0
}

# 1. app in public mode (env var applies to the app process started below only)
& (Join-Path $PSScriptRoot 'stop.ps1') | Out-Null
$env:PUBLIC_MODE = '1'
try { & (Join-Path $PSScriptRoot 'start.ps1') } finally { Remove-Item Env:\PUBLIC_MODE -ErrorAction SilentlyContinue }
if ($LASTEXITCODE -ne 0 -or -not (Test-Health)) { Write-Error "The app did not start."; exit 1 }

# 2. tunnel
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
Remove-Item $TunnelLog, $UrlFile -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $Cloudflared -WindowStyle Hidden -PassThru `
    -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://${AppHost}:${AppPort}" `
    -RedirectStandardError $TunnelLog -RedirectStandardOutput (Join-Path $RunDir 'tunnel.out.log')
@{ pid = $proc.Id; started = $proc.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json |
    Set-Content -Path $TunnelPid -Encoding ascii

Write-Host -NoNewline "Opening public link"
$url = $null
for ($i = 0; $i -lt 90 -and -not $url; $i++) {
    Start-Sleep -Seconds 1; Write-Host -NoNewline '.'
    if ($proc.HasExited) { break }
    $m = Select-String -Path $TunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value }
}
Write-Host ""
if (-not $url) {
    Write-Error "The tunnel did not start. Last log lines:"; Get-Content $TunnelLog -Tail 15 -ErrorAction SilentlyContinue
    & (Join-Path $PSScriptRoot 'public_stop.ps1') | Out-Null
    exit 1
}
Set-Content -Path $UrlFile -Value $url -Encoding ascii
Write-Host ""
Write-Host "  DermaCareAI is public at:  $url" -ForegroundColor Green
Write-Host "  (it can take up to a minute before the link answers)"
Write-Host "  Stop it with: .\scripts\public_stop.ps1"
