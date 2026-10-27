#!/usr/bin/env bash
# Hive TEXTFILE vs RCFile benchmark. Execute INSIDE the master container:
#   docker exec master bash /project/hive/benchmark_hive.sh                 (obs_text, obs_rc; 3 runs)
#   docker exec -e TABLES="obs_text obs_rc obs_rc_snappy obs_orc" master bash /project/hive/benchmark_hive.sh
# Wall-clock time = the time HiveServer2 reports to beeline for each query ("N rows selected (X seconds)").
# HDFS bytes read = sum of HDFS_BYTES_READ over the MapReduce jobs launched by that query (JobHistory REST API).
set -uo pipefail
cd /project
TABLES=${TABLES:-"obs_text obs_rc"}
RUNS=${RUNS:-3}
URL="jdbc:hive2://${MASTER_HOST:-master}:10000/ghcn"
RAW=results/hive_runs_raw.csv
LOG=results/logs/hive_benchmark.log
mkdir -p results/logs /tmp/hq

[ -f "$RAW" ] || echo "table,query,run,seconds,rows,t0_ms,t1_ms" > "$RAW"

# split the query file on "-- @Qn" markers
awk '/^-- @Q/{q=$2; next} q && NF && !/^--/{print > "/tmp/hq/" q ".sql"}' hive/benchmark_queries.hql
QUERIES=$(ls /tmp/hq | sed 's/.sql//' | sort)

for tbl in $TABLES; do
  for q in $QUERIES; do
    for r in $(seq 1 "$RUNS"); do
      sed "s/\${TBL}/$tbl/g" /tmp/hq/$q.sql > /tmp/hq/run.sql
      t0=$(date +%s%3N)
      out=$(beeline -u "$URL" -n root --silent=false --showHeader=true --outputformat=tsv2 -f /tmp/hq/run.sql 2>&1)
      t1=$(date +%s%3N)
      secs=$(echo "$out" | grep -oP '\(\K[0-9.]+(?= seconds\))' | tail -1)
      rows=$(echo "$out" | grep -oP '^[0-9,]+(?= rows? selected)|^No(?= rows selected)' | tail -1 | tr -d ',')
      [ "$rows" = "No" ] && rows=0
      if [ -z "$secs" ]; then echo "$out" | tail -20 >> "$LOG"; echo "FAILED $tbl $q run $r (see $LOG)"; continue; fi
      echo "$tbl,$q,$r,$secs,$rows,$t0,$t1" >> "$RAW"
      printf '%-14s %-3s run %d  %8.2f s  rows=%s\n' "$tbl" "$q" "$r" "$secs" "$rows" | tee -a "$LOG"
      if [ "$r" = "1" ]; then
        { echo "----- $tbl $q result -----"; echo "$out" | grep -v -E '^(SLF4J|Connecting|Connected|Driver|Transaction|Beeline|Closing|INFO|WARN|0: jdbc)' | head -25; } >> results/logs/hive_query_results.log
      fi
    done
  done
done

echo; echo "=== Storage per table ==="
echo "table,bytes,bytes_with_replicas,files" > results/hive_storage.csv
for tbl in obs_text obs_rc obs_rc_snappy obs_orc monthly_summary; do
  loc=$( [ "$tbl" = obs_text ] && echo /ghcn/clean || echo /user/hive/warehouse/ghcn.db/$tbl )
  if hdfs dfs -test -d "$loc" 2>/dev/null; then
    read -r b br _ < <(hdfs dfs -du -s "$loc" 2>/dev/null)
    files=$(hdfs dfs -count "$loc" 2>/dev/null | awk '{print $2}')
    echo "$tbl,$b,$br,$files" >> results/hive_storage.csv
    hdfs dfs -du -s -h "$loc" 2>/dev/null | sed "s|^|$tbl  |"
  fi
done

echo; echo "=== Collecting job counters from JobHistory ==="
sleep 10
python3 hive/collect_counters.py
