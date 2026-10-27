# Alternative to ingest.py: bulk-load the station JSON Lines file with the mongoimport CLI
# (ships inside the mongo image). Loads into a separate collection so ingest.py's data is untouched.
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)
$t0 = Get-Date
Get-Content data\stations.jsonl -Raw | docker exec -i mongodb mongoimport --db ghcn --collection stations_import --drop --numInsertionWorkers 4
Write-Host ("mongoimport took {0:N1} s" -f ((Get-Date) - $t0).TotalSeconds)
docker exec mongodb mongosh --quiet ghcn --eval "printjson({stations_import: db.stations_import.countDocuments(), sample: db.stations_import.findOne({station_id: 'IN009010100'}, {_id: 0, station_id: 1, name: 1, location: 1, country_name: 1})})"
# For CSV the equivalent is:
#   docker exec -i mongodb mongoimport --db ghcn --collection stations_csv --type csv --headerline --drop < data\stations.csv
