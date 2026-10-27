# Downloads the Hadoop, Hive and Pig release tarballs (once) into docker\hadoop\tarballs.
# native tools (docker, curl) write progress to stderr; PowerShell 5.1 must not treat that as an error
$ErrorActionPreference = 'Continue'
$dir = Join-Path (Split-Path $PSScriptRoot -Parent) "docker\hadoop\tarballs"
New-Item -ItemType Directory -Force $dir | Out-Null
$files = [ordered]@{
    "hadoop-3.3.6.tar.gz"          = "https://dlcdn.apache.org/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz"
    # Hive 3.1.3 is no longer on the Apache CDN and archive.apache.org is heavily throttled;
    # this public mirror serves the identical file (sha256 0c9b6a63...bb16, verified against Apache).
    "apache-hive-3.1.3-bin.tar.gz" = "https://repo.huaweicloud.com/apache/hive/hive-3.1.3/apache-hive-3.1.3-bin.tar.gz"
    "pig-0.18.0.tar.gz"            = "https://dlcdn.apache.org/pig/pig-0.18.0/pig-0.18.0.tar.gz"
    "postgresql-42.7.4.jar"        = "https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar"
}
foreach ($f in $files.Keys) {
    $out = Join-Path $dir $f
    if (Test-Path $out) { Write-Host "already have $f"; continue }
    Write-Host "downloading $f ..."
    # curl.exe ships with Windows 10/11 and supports resume (-C -)
    curl.exe -fL --retry 5 -C - -o $out $files[$f]
    if ($LASTEXITCODE -ne 0) { throw "download failed: $f" }
}
