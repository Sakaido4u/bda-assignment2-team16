# Starts the 3-node cluster (Mode A) and waits until 2 DataNodes and 2 NodeManagers are live.
# Usage:  .\scripts\start-cluster.ps1            (build image if missing, then start)
#         .\scripts\start-cluster.ps1 -Rebuild   (force image rebuild)
param([switch]$Rebuild, [int]$TimeoutSec = 600)
# native tools (docker, curl) write progress to stderr; PowerShell 5.1 must not treat that as an error
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)

docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker Desktop is not running. Start it first." -ForegroundColor Red; exit 1 }

$tar = "docker\hadoop\tarballs"
if (-not (Test-Path "$tar\hadoop-3.3.6.tar.gz") -or -not (Test-Path "$tar\apache-hive-3.1.3-bin.tar.gz") -or -not (Test-Path "$tar\pig-0.18.0.tar.gz")) {
    Write-Host "Hadoop/Hive/Pig tarballs missing - downloading..." -ForegroundColor Yellow
    & "$PSScriptRoot\fetch-tarballs.ps1"
}

docker image inspect bda16/hadoop:3.3.6 *> $null
if ($Rebuild -or $LASTEXITCODE -ne 0) {
    Write-Host "Building images (first time takes a few minutes)..." -ForegroundColor Cyan
    docker compose build master dashboard
    if ($LASTEXITCODE -ne 0) { throw "image build failed" }
}

Write-Host "Starting containers..." -ForegroundColor Cyan
docker compose up -d metastore-db master worker1 worker2 mongodb dashboard
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "Waiting for 2 live DataNodes and 2 running NodeManagers (NameNode is formatted only on first run)..."
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$dn = 0; $nm = 0
while ((Get-Date) -lt $deadline) {
    $report = docker exec master bash -c "hdfs dfsadmin -report 2>/dev/null | grep -E '^Live datanodes'"
    if ($report -match '\((\d+)\)') { $dn = [int]$Matches[1] }
    $nodes = docker exec master bash -c "yarn node -list 2>/dev/null | grep -E 'Total Nodes'"
    if ($nodes -match 'Total Nodes:(\d+)') { $nm = [int]$Matches[1] }
    Write-Host ("  live DataNodes: {0}/2   running NodeManagers: {1}/2" -f $dn, $nm)
    if ($dn -ge 2 -and $nm -ge 2) { break }
    Start-Sleep -Seconds 5
}
if ($dn -lt 2 -or $nm -lt 2) {
    Write-Host "Cluster did not become healthy in $TimeoutSec s. Check: docker compose logs master worker1 worker2" -ForegroundColor Red
    exit 1
}

Write-Host "Waiting for HiveServer2 on port 10000..."
for ($i = 0; $i -lt 60; $i++) {
    docker exec master bash -c "nc -z localhost 10000" *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "CLUSTER READY - 1 master + 2 workers" -ForegroundColor Green
Write-Host "  NameNode UI        http://localhost:9870"
Write-Host "  ResourceManager UI http://localhost:8088"
Write-Host "  JobHistory UI      http://localhost:19888"
Write-Host "  DataNode UIs       http://localhost:9864 (worker1)  http://localhost:9865 (worker2)"
Write-Host "  NodeManager UIs    http://localhost:8042 (worker1)  http://localhost:8043 (worker2)"
Write-Host "  HiveServer2 UI     http://localhost:10002"
Write-Host "  Dashboard          http://localhost:5000"
