#!/usr/bin/env bash
# Linux / WSL2 / native-install equivalent of download-data.ps1
# Usage: ./scripts/download-data.sh [START_YEAR] [END_YEAR]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
START=${1:-$GHCN_START_YEAR}
END=${2:-$GHCN_END_YEAR}
BASE=https://www.ncei.noaa.gov/pub/data/ghcn/daily
mkdir -p data/raw
for f in ghcnd-stations.txt ghcnd-countries.txt ghcnd-inventory.txt; do
  curl -fL --retry 5 -o "data/raw/$f" "$BASE/$f"
done
for y in $(seq "$START" "$END"); do
  curl -fL --retry 5 -C - -o "data/raw/$y.csv.gz" "$BASE/by_year/$y.csv.gz" || [ $? -eq 33 ]
done
python3 scripts/prepare_stations.py
ls -lh data/raw data
