#!/usr/bin/env bash
# Runs the Pig scripts in MapReduce mode. Execute INSIDE the master container:
#   docker exec master bash /project/pig/run-pig.sh
set -uo pipefail
cd /project
mkdir -p results/logs
export PIG_OPTS="-Dmapreduce.map.memory.mb=512 -Dmapreduce.reduce.memory.mb=512"

echo "=== Building a small sample (5000 core rows incl. QC-failed rows from India and elsewhere) ==="
hdfs dfs -mkdir -p /ghcn/sample
LATEST=$(ls data/raw/[12][0-9][0-9][0-9].csv.gz | sort | tail -1)
{ zcat "$LATEST" | head -n 3000; zcat "$LATEST" | grep -m 1500 '^IN' ; zcat "$LATEST" | awk -F, '$6!=""' | head -n 500; } \
  > /tmp/sample.csv
hdfs dfs -put -f /tmp/sample.csv /ghcn/sample/sample.csv
wc -l /tmp/sample.csv

echo "=== Pig sample inspection (DESCRIBE / DUMP / ILLUSTRATE) ==="
pig -x mapreduce -f pig/inspect_sample.pig > results/logs/pig_inspect_sample.log 2>&1
grep -v -E '^[0-9-]+ [0-9:,]+ (\[[A-Za-z]+\] )?(INFO|WARN)|^\s*at |SLF4J' results/logs/pig_inspect_sample.log | sed '/^$/d' | head -120

echo; echo "=== Full cleaning job: /ghcn/raw -> /ghcn/clean ==="
t0=$(date +%s)
pig -x mapreduce -param INPUT=/ghcn/raw -param OUTPUT=/ghcn/clean -f pig/clean_ghcn.pig > results/logs/pig_clean.log 2>&1
rc=$?
t1=$(date +%s)
sed -n '/HadoopVersion/,/Job DAG/p' results/logs/pig_clean.log
grep -E 'Successfully (read|stored)|Success!|Failed!' results/logs/pig_clean.log
echo "pig exit=$rc  elapsed=$((t1-t0))s"
[ $rc -eq 0 ] || exit 1

echo; echo "=== Record counts before / after cleaning ==="
# GROUP ALL over an empty relation emits no row, so a stage with 0 records is added explicitly
hdfs dfs -cat '/ghcn/clean_stats/part-*' 2>/dev/null | sort > /tmp/counts.tsv
for st in 1_raw_records 2_core_elements 3_qc_failed_removed 4_missing_removed 5_clean_records; do
  grep -q "^$st" /tmp/counts.tsv || printf '%s	0
' "$st" >> /tmp/counts.tsv
done
sort /tmp/counts.tsv | tee results/pig_clean_counts.tsv
echo "pig_clean_seconds	$((t1-t0))" >> results/pig_clean_counts.tsv
echo; hdfs dfs -du -s -h /ghcn/raw /ghcn/clean
echo "first cleaned rows:"; hdfs dfs -cat "$(hdfs dfs -ls /ghcn/clean 2>/dev/null | awk '/part-/{print $NF; exit}')" 2>/dev/null | head -5
