# Prints the evidence that all 3 nodes are working together.
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "===== Containers =====" -ForegroundColor Cyan
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n===== HDFS: hdfs dfsadmin -report (expect 'Live datanodes (2)') =====" -ForegroundColor Cyan
docker exec master bash -c "hdfs dfsadmin -report 2>/dev/null"

Write-Host "`n===== YARN: yarn node -list (expect 2 RUNNING nodes) =====" -ForegroundColor Cyan
docker exec master bash -c "yarn node -list -all 2>/dev/null"

Write-Host "`n===== Java daemons per node (jps) =====" -ForegroundColor Cyan
foreach ($n in 'master', 'worker1', 'worker2') {
    Write-Host "--- $n ---"
    docker exec $n bash -c "jps | grep -v Jps | sort -k2"
}
