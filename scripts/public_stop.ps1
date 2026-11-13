# PUBLIC STOP: closes the public link and switches the app back to normal local-only mode.
. (Join-Path $PSScriptRoot '_common.ps1')
$Cloudflared = Join-Path $Root 'tools\cloudflared.exe'
$TunnelPid = Join-Path $RunDir 'tunnel.pid'
$UrlFile = Join-Path $RunDir 'public_url.txt'

$stopped = $false
if (Test-Path $TunnelPid) {
    try { $info = Get-Content $TunnelPid -Raw | ConvertFrom-Json } catch { $info = $null }
    if ($info) {
        $p = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
        # only stop OUR cloudflared (path + start time match), never anything else
        if ($p -and $p.Path -ieq $Cloudflared -and $p.StartTime.ToUniversalTime().ToString('o') -eq $info.started) {
            Stop-Process -Id $p.Id -Force
            $stopped = $true
        }
    }
    Remove-Item $TunnelPid -Force -ErrorAction SilentlyContinue
}
Remove-Item $UrlFile -ErrorAction SilentlyContinue
Write-Host $(if ($stopped) { "Public link closed." } else { "No public link was running." })

# restart the app without PUBLIC_MODE (local access only, plain cookies)
& (Join-Path $PSScriptRoot 'restart.ps1')
