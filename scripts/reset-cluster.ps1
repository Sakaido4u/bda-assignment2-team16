# Removes the containers AND the named volumes (HDFS, MongoDB, Hive metastore). Irreversible.
param([switch]$Force)
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $Force) {
    $answer = Read-Host "This deletes ALL HDFS, MongoDB and Hive metastore data. Type YES to continue"
    if ($answer -ne 'YES') { Write-Host "Aborted."; exit 0 }
}
docker compose --profile tools down -v --remove-orphans
Write-Host "Cluster reset. The next start-cluster.ps1 will format a fresh NameNode." -ForegroundColor Yellow
