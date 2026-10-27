#!/usr/bin/env bash
# Whole Theme 3 Hive phase. Execute INSIDE the master container after pig/run-pig.sh:
#   docker exec master bash /project/hive/run-hive.sh
#   BONUS=0 skips the Snappy-RCFile / ORC / summary tables; BONUS_RUNS sets their benchmark runs (default 1)
set -uo pipefail
cd /project
mkdir -p results/logs
URL="jdbc:hive2://${MASTER_HOST:-master}:10000"
BONUS=${BONUS:-1}

echo "=== 1. TEXTFILE + RCFile tables ==="
t0=$(date +%s)
beeline -u "$URL" -n root -f hive/01_create_tables.hql > results/logs/hive_create_tables.log 2>&1 || { tail -30 results/logs/hive_create_tables.log; exit 1; }
echo "create + INSERT OVERWRITE took $(( $(date +%s) - t0 )) s"
grep -E '^\| obs_' results/logs/hive_create_tables.log

if [ "$BONUS" = 1 ]; then
  echo "=== 2. BONUS tables (Snappy RCFile, ORC, monthly_summary) ==="
  t0=$(date +%s)
  beeline -u "$URL" -n root -f hive/02_bonus_tables.hql > results/logs/hive_bonus_tables.log 2>&1 || { tail -30 results/logs/hive_bonus_tables.log; exit 1; }
  echo "bonus tables took $(( $(date +%s) - t0 )) s"
  grep -E 'summary_rows|^\| [0-9]' results/logs/hive_bonus_tables.log | tail -3
fi

echo "=== 3. Benchmark: TEXTFILE vs RCFile, 3 runs each ==="
rm -f results/hive_runs_raw.csv results/logs/hive_benchmark.log results/logs/hive_query_results.log
TABLES="obs_text obs_rc" RUNS=3 bash hive/benchmark_hive.sh
if [ "$BONUS" = 1 ]; then
  echo "=== 4. BONUS benchmark: Snappy RCFile and ORC ==="
  TABLES="obs_rc_snappy obs_orc" RUNS=${BONUS_RUNS:-1} bash hive/benchmark_hive.sh
fi
