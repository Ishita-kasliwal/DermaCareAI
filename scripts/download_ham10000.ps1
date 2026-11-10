# Downloads HAM10000 (CC BY-NC 4.0) from the official Harvard Dataverse record
# doi:10.7910/DVN/DBW86T into ml\data\raw\HAM10000, verifies MD5, and extracts.
# Total download is about 2.8 GB. Re-running resumes or skips completed files.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root 'ml\data\raw\HAM10000'
$Dl   = Join-Path $Dest '_downloads'
New-Item -ItemType Directory -Force -Path $Dl | Out-Null

$Api = 'https://dataverse.harvard.edu/api/access/datafile'
$files = @(
    @{ id = 3172585; name = 'HAM10000_images_part_1.zip'; md5 = '4639bfa73ab251610530a97c898e6e46'; dir = 'HAM10000_images_part_1' },
    @{ id = 3172584; name = 'HAM10000_images_part_2.zip'; md5 = 'da43d6cc50f6613013be07e8986b384b'; dir = 'HAM10000_images_part_2' }
)

Write-Host "License: CC BY-NC 4.0 (non-commercial, attribution required). See docs\DATASETS.md"

foreach ($f in $files) {
    $zip = Join-Path $Dl $f.name
    $ok = (Test-Path $zip) -and ((Get-FileHash $zip -Algorithm MD5).Hash.ToLower() -eq $f.md5)
    if (-not $ok) {
        Write-Host "Downloading $($f.name) ..."
        # Slow or unstable connections drop often: keep resuming (-C -) from where it stopped.
        $attempt = 0
        do {
            $attempt++
            if ($attempt -gt 1) { Write-Host "Connection dropped; resuming (attempt $attempt of 200) in 15 s..."; Start-Sleep -Seconds 15 }
            & curl.exe -L --fail --retry 10 --retry-all-errors --retry-delay 10 --speed-limit 1000 --speed-time 120 -C - -o $zip "$Api/$($f.id)"
        } while ($LASTEXITCODE -ne 0 -and $attempt -lt 200)
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $($f.name)" }
        $hash = (Get-FileHash $zip -Algorithm MD5).Hash.ToLower()
        if ($hash -ne $f.md5) { throw "MD5 mismatch for $($f.name): $hash (expected $($f.md5)). Delete it and re-run." }
    }
    Write-Host "Verified $($f.name)"
    $out = Join-Path $Dest $f.dir
    if (-not (Test-Path $out) -or -not (Get-ChildItem $out -Filter *.jpg -Recurse | Select-Object -First 1)) {
        New-Item -ItemType Directory -Force -Path $out | Out-Null
        Write-Host "Extracting to $out ..."
        & tar.exe -xf $zip -C $out
        if ($LASTEXITCODE -ne 0) { throw "Extraction failed: $($f.name)" }
    }
}

$meta = Join-Path $Dest 'HAM10000_metadata.csv'
if (-not (Test-Path $meta)) {
    Write-Host "Downloading metadata (original CSV) ..."
    & curl.exe -L --fail --retry 5 -o $meta "$Api/4338392?format=original"
    if ($LASTEXITCODE -ne 0) { throw "Metadata download failed" }
}
$header = (Get-Content $meta -TotalCount 1)
foreach ($col in 'lesion_id', 'image_id', 'dx') {
    if ($header -notmatch "\b$col\b") { throw "Metadata header missing '$col': $header" }
}
$rows = (Get-Content $meta | Measure-Object -Line).Lines - 1
$jpgs = (Get-ChildItem $Dest -Recurse -Filter *.jpg | Measure-Object).Count
Write-Host "Metadata rows: $rows   JPEG files: $jpgs"
Write-Host "Done. You can delete $Dl to free ~2.8 GB once extraction is verified."
