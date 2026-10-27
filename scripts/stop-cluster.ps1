# Stops all containers. HDFS, MongoDB and metastore data stay in the named volumes.
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose stop
Write-Host "Cluster stopped. Data is kept - run .\scripts\start-cluster.ps1 to resume." -ForegroundColor Green
