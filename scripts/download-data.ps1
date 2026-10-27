# Downloads NOAA GHCN-Daily station metadata + by_year files into .\data\raw
# Usage: .\scripts\download-data.ps1                      (years from .env, default 2023-2025)
#        .\scripts\download-data.ps1 -StartYear 2015 -EndYear 2025
param([int]$StartYear = 0, [int]$EndYear = 0)
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# read defaults from .env
$envMap = @{}
Get-Content .env | Where-Object { $_ -match '^\s*([A-Z0-9_]+)=(.*)$' } | ForEach-Object { $envMap[$Matches[1]] = $Matches[2] }
if ($StartYear -eq 0) { $StartYear = [int]$envMap['GHCN_START_YEAR'] }
if ($EndYear -eq 0) { $EndYear = [int]$envMap['GHCN_END_YEAR'] }

$base = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
$raw = Join-Path $root "data\raw"
New-Item -ItemType Directory -Force $raw | Out-Null

$files = @("ghcnd-stations.txt", "ghcnd-countries.txt", "ghcnd-inventory.txt")
foreach ($y in $StartYear..$EndYear) { $files += "by_year/$y.csv.gz" }

foreach ($f in $files) {
    $out = Join-Path $raw (Split-Path $f -Leaf)
    Write-Host "downloading $f ..."
    curl.exe -fL --retry 5 -C - -o $out "$base/$f"
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 33) { Write-Host "FAILED: $f" -ForegroundColor Red; exit 1 }
}

Write-Host "Converting stations file to CSV / TSV / JSON ..."
docker compose run --rm tools python scripts/prepare_stations.py
Get-ChildItem $raw, (Join-Path $root "data") -File | Format-Table Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
