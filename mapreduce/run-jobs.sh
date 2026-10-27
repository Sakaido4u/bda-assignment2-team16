#!/usr/bin/env bash
# Runs the Theme 2 MapReduce jobs on YARN. Execute INSIDE the master container:
#   docker exec master bash /project/mapreduce/run-jobs.sh
# Prerequisites: scripts/hdfs-operations.sh has loaded /ghcn/raw, and mapreduce/build.ps1 has built the jar.
set -uo pipefail
cd /project
JAR=mapreduce/target/ghcn-mapreduce.jar
IN=/ghcn/raw
OUT=/ghcn/output
LOGDIR=results/logs
SAMPLES=mapreduce/sample-output
TIMES=results/mapreduce_times.csv
mkdir -p "$LOGDIR" "$SAMPLES"
[ -f "$JAR" ] || { echo "missing $JAR - run mapreduce/build.ps1 first"; exit 1; }
STREAMING_JAR=$(ls $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar)

echo "job,implementation,input,wall_seconds,job_id,maps,reduces,hdfs_bytes_read,map_output_records,combine_output_records,reduce_shuffle_bytes" > "$TIMES"
JOB_IDS=()

record() {   # name impl logfile seconds
  local jid maps reds hbr mor cor rsb
  jid=$(grep -o 'job_[0-9]*_[0-9]*' "$3" | head -1)
  maps=$(grep -oP 'Launched map tasks=\K[0-9]+' "$3" | head -1)
  reds=$(grep -oP 'Launched reduce tasks=\K[0-9]+' "$3" | head -1)
  hbr=$(grep -oP 'HDFS: Number of bytes read=\K[0-9]+' "$3" | head -1)
  mor=$(grep -oP 'Map output records=\K[0-9]+' "$3" | head -1)
  cor=$(grep -oP 'Combine output records=\K[0-9]+' "$3" | head -1)
  rsb=$(grep -oP 'Reduce shuffle bytes=\K[0-9]+' "$3" | head -1)
  echo "$1,$2,$IN,$4,$jid,$maps,$reds,$hbr,$mor,$cor,$rsb" >> "$TIMES"
  JOB_IDS+=("$jid")
  echo ">>> $1 ($2) finished in ${4}s  job=$jid maps=$maps reduces=$reds"
}

timed() {    # name impl logfile command...
  local name=$1 impl=$2 log=$3; shift 3
  echo; echo "=== $name ($impl) ==="; echo "\$ $*"
  local t0=$(date +%s.%N)
  "$@" > "$log" 2>&1
  local rc=$?
  local t1=$(date +%s.%N)
  grep -E 'Running job|map [0-9]+% reduce|completed successfully|Launched|Data-local|Rack-local|VALID|MALFORMED|QC_FAILED|MISSING_VALUE|OTHER_ELEMENT|EXTREME_DAYS|PRCP_READINGS|HDFS: Number of bytes read|Map output records|Combine output records|Reduce output records' "$log" | sed 's/^/    /'
  [ $rc -eq 0 ] || { echo "job failed - see $log"; exit 1; }
  record "$name" "$impl" "$log" "$(python3 -c "print(round($t1-$t0,1))")"
}

timed "job1_country_year_temp" "java" "$LOGDIR/mr_job1_java.log" \
  hadoop jar "$JAR" country-temp -D ghcn.reducers=2 "$IN" "$OUT/job1_country_temp_java"

timed "job2_extreme_precip" "java" "$LOGDIR/mr_job2_java.log" \
  hadoop jar "$JAR" extreme-precip -D ghcn.prcp.threshold=500 -D ghcn.reducers=2 "$IN" "$OUT/job2_extreme_precip_java"

hdfs dfs -rm -r -f -skipTrash "$OUT/job1_country_temp_streaming" >/dev/null 2>&1
timed "job1_country_year_temp" "python_streaming" "$LOGDIR/mr_job1_streaming.log" \
  hadoop jar "$STREAMING_JAR" \
    -D mapreduce.job.name="GHCN Job1 - yearly avg TMAX/TMIN per country (Python Streaming)" \
    -D mapreduce.job.reduces=2 \
    -files mapreduce/streaming/mapper.py,mapreduce/streaming/combiner.py,mapreduce/streaming/reducer.py \
    -mapper "python3 mapper.py" -combiner "python3 combiner.py" -reducer "python3 reducer.py" \
    -input "$IN" -output "$OUT/job1_country_temp_streaming"

echo; echo "=== Collecting outputs ==="
hdfs dfs -cat "$OUT/job1_country_temp_java/part-*" 2>/dev/null | sort > "$SAMPLES/job1_country_temp_java.tsv"
hdfs dfs -cat "$OUT/job1_country_temp_streaming/part-*" 2>/dev/null | sort > "$SAMPLES/job1_country_temp_streaming.tsv"
hdfs dfs -cat "$OUT/job2_extreme_precip_java/part-*" 2>/dev/null | sort -t$'\t' -k2,2nr > "$SAMPLES/job2_extreme_precip_java.tsv"
wc -l "$SAMPLES"/*.tsv
if diff -q "$SAMPLES/job1_country_temp_java.tsv" "$SAMPLES/job1_country_temp_streaming.tsv" >/dev/null; then
  echo "Java and Python Streaming outputs are IDENTICAL"
else
  # Java's String.format rounds half-up, Python's f-string rounds the binary float - ties can differ by 0.01
  paste "$SAMPLES/job1_country_temp_java.tsv" "$SAMPLES/job1_country_temp_streaming.tsv" | awk -F'\t' '
    { n++; if ($1!=$7 || $2!=$8 || $5!=$11 || $6!=$12) bad++;
      else if (($3!="NaN" && ($3-$9>0.0101 || $9-$3>0.0101)) || ($4!="NaN" && ($4-$10>0.0101 || $10-$4>0.0101))) bad++;
      else if ($3!=$9 || $4!=$10) tie++ }
    END { printf "Java vs Streaming: %d rows, %d differ beyond rounding, %d differ only by a 0.01 rounding tie\n", n, bad+0, tie+0 }'
fi
echo; echo "India (IN) yearly averages:"; grep -P '^IN\t' "$SAMPLES/job1_country_temp_java.tsv"
echo; echo "Top 10 stations by extreme-precipitation days (>= 50 mm):"; head -10 "$SAMPLES/job2_extreme_precip_java.tsv"

echo; echo "=== Which node ran each task (JobHistory REST API) ==="
sleep 5
rm -f results/mr_task_nodes.csv
python3 mapreduce/task_nodes.py "${JOB_IDS[@]}" | tee "$LOGDIR/mr_task_nodes.log"
echo; cat "$TIMES"
