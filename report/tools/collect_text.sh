#!/usr/bin/env bash
# Slices the run logs (and a few live commands) into short text files that capture.py renders
# as terminal screenshots.  Usage (Git Bash / Linux, from the project root):
#   bash report/tools/collect_text.sh <phase>      phase = cluster|hdfs|mr|pig|hive|mongo
set -uo pipefail
export MSYS_NO_PATHCONV=1
T=report/screenshots/text
mkdir -p "$T"
L=results/logs

section() {  # log "start regex" "end regex" -> stdout (start inclusive, end exclusive)
  S="$2" E="$3" awk '$0 ~ ENVIRON["S"] {on=1} on && ENVIRON["E"] != "" && $0 ~ ENVIRON["E"] && !($0 ~ ENVIRON["S"]) {exit} on {print}' "$1" \
    | grep -v -E '^={10,}$'
}
dx() { docker exec "$@" 2>/dev/null; }

case "${1:-}" in
cluster)
  { echo '$ docker compose ps'; docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'; } > $T/c01_compose_ps.txt
  { echo '$ docker exec master hdfs dfsadmin -report'; dx master hdfs dfsadmin -report | grep -v -E 'Cache|Erasure|block groups|Low redundancy|Pending deletion|Missing blocks \(with'; } > $T/c02_dfsadmin_report.txt
  { echo '$ docker exec master yarn node -list -all'; dx master yarn node -list -all;
    for n in master worker1 worker2; do echo; echo "\$ docker exec $n jps"; dx $n bash -c "jps | grep -v Jps | sort -k2"; done; } > $T/c03_yarn_nodes_jps.txt
  { echo '$ docker exec master hdfs getconf -confKey dfs.replication / dfs.blocksize / fs.defaultFS'
    for k in fs.defaultFS dfs.replication dfs.blocksize yarn.nodemanager.resource.memory-mb mapreduce.map.memory.mb; do
      printf '%-40s %s\n' "$k" "$(dx master hdfs getconf -confKey $k)"; done
    echo; echo '$ docker exec master cat /opt/hadoop/etc/hadoop/workers'; dx master cat /opt/hadoop/etc/hadoop/workers
    echo; echo '$ docker exec master bash -c "hadoop version | head -1; hive --version 2>/dev/null | head -1; pig -version 2>/dev/null | head -1"'
    dx master bash -c "hadoop version | head -1; hive --version 2>/dev/null | head -1; pig -version 2>/dev/null | grep -i 'Apache Pig'"; } > $T/c04_config_versions.txt
  ;;
hdfs)
  section $L/hdfs_operations.log '## 1\.' '## 4\.' > $T/h01_mkdir_put.txt
  section $L/hdfs_operations.log '## 4\.' '## 6\.' > $T/h02_ls_du.txt
  section $L/hdfs_operations.log '## 6\.' '## 9\.' > $T/h03_cat_get_rm.txt
  section $L/hdfs_operations.log '## 9\.' '\(full fsck' | cut -c1-230 > $T/h04_stat_fsck_blocks.txt
  section $L/hdfs_operations.log '\(full fsck' 'HDFS operations finished' > $T/h05_fsck_summary_per_node.txt
  ;;
mr)
  { echo '$ .\mapreduce\build.ps1   (mvn -B package inside maven:3.9.9-eclipse-temurin-8)'; echo
    echo '$ docker exec master jar tf /project/mapreduce/target/ghcn-mapreduce.jar | grep class'
    dx master bash -c "cd /tmp && /opt/java/openjdk/bin/jar tf /project/mapreduce/target/ghcn-mapreduce.jar | grep class"
    echo; ls -l mapreduce/target/ghcn-mapreduce.jar; } > $T/m00_build_jar.txt
  section $L/run_jobs_console.log '=== job1_country_year_temp \(java\)' '=== job2' | grep -v -E 'map [0-9]+% reduce [0-9]+%$' > $T/m01_job1_java.txt
  grep -E 'map (0|25|50|75|100)% reduce' $L/mr_job1_java.log | sed 's/^/    /' | head -12 >> $T/m01_job1_java.txt
  section $L/run_jobs_console.log '=== job2_extreme_precip' '=== job1_country_year_temp \(python' | grep -v -E 'map [0-9]+% reduce [0-9]+%$' > $T/m02_job2_java.txt
  section $L/run_jobs_console.log '=== job1_country_year_temp \(python' '=== Collecting' | grep -v -E 'map [0-9]+% reduce [0-9]+%$' > $T/m03_job1_streaming.txt
  { section $L/run_jobs_console.log '=== Collecting' '=== Which node'; cat $L/mr_java_vs_streaming_check.log 2>/dev/null; } | grep -v 'differ:' | grep -v -E '^(<|>|---|[0-9]+c[0-9]+)' > $T/m04_outputs.txt
  { section $L/run_jobs_console.log '=== Which node' 'job,implementation'; echo; echo '$ cat results/mapreduce_times.csv'; cut -d, -f1-8 results/mapreduce_times.csv | column -t -s,; } > $T/m05_task_nodes.txt
  { echo '$ hdfs dfs -cat /ghcn/output/job1_country_temp_java/part-r-00000 | head -20   (country  year  avgTMAX  avgTMIN  nTMAX  nTMIN)'
    dx master bash -c "hdfs dfs -cat /ghcn/output/job1_country_temp_java/part-r-00000 | head -20"
    echo; echo '$ hdfs dfs -ls /ghcn/output/job1_country_temp_java /ghcn/output/job1_country_temp_streaming'
    dx master hdfs dfs -ls /ghcn/output/job1_country_temp_java /ghcn/output/job1_country_temp_streaming; } > $T/m06_hdfs_output.txt
  ;;
pig)
  F='^[0-9-]+ [0-9:,]+ (\[[A-Za-z]+\] )?(INFO|WARN)|^\s*at |SLF4J|ExecTypeProvider'
  { echo '$ pig -x mapreduce -f pig/inspect_sample.pig     (DESCRIBE, DUMP on a 5,000-row sample)'
    grep -v -E "$F" $L/pig_inspect_sample.log | sed '/^$/d' | awk '/^-{20,}/{exit} {print}' | grep -v -E 'Spillable|proactively|Total (records|bytes) written|^Counters:' ; } > $T/p01_describe_dump.txt
  { echo '$ pig -x mapreduce -f pig/inspect_sample.pig     (ILLUSTRATE clean)'; awk '/^-{20,}/{on=1} on{print}' $L/pig_inspect_sample.log | cut -c1-230 | head -48; } > $T/p02_illustrate.txt
  { echo '$ pig -x mapreduce -param INPUT=/ghcn/raw -param OUTPUT=/ghcn/clean -f pig/clean_ghcn.pig'
    grep -v -E "$F" $L/pig_clean.log | sed '/^$/d' | grep -v -E 'Spillable|Total bags|Total records proactively' | cut -c1-240; } > $T/p03_clean_job_stats.txt
  { echo '$ hdfs dfs -cat /ghcn/clean_stats/part-*      (records at each cleaning stage)'; cat results/pig_clean_counts.tsv
    echo; echo '$ hdfs dfs -du -s -h /ghcn/raw /ghcn/clean'; dx master hdfs dfs -du -s -h /ghcn/raw /ghcn/clean
    echo; echo '$ hdfs dfs -ls /ghcn/clean | head'; dx master bash -c "hdfs dfs -ls /ghcn/clean | head -8"
    echo; echo '$ hdfs dfs -cat /ghcn/clean/part-m-00121 | head -5   (station country year month day element value m s time)'
    dx master bash -c "hdfs dfs -cat /ghcn/clean/part-m-00121 2>/dev/null | head -5"; } > $T/p04_counts.txt
  ;;
hive)
  { echo '$ beeline -u jdbc:hive2://master:10000 -n root -f hive/01_create_tables.hql'; grep -v -E '^(SLF4J|INFO|WARN)|^\s*$|Hadoop job information|Stage-Stage|^Ended Job|Total jobs|Launching Job|In order to|set hive|set mapreduce|Starting Job|Kill Command|Number of reduce tasks|Estimated from|Query ID|Total MapReduce CPU|MapReduce Jobs Launched|^Stage-[0-9]+:' $L/hive_create_tables.log | cut -c1-200 | tail -60; } > $T/v01_create_tables.txt
  { echo '$ beeline ... -e "USE ghcn; SHOW TABLES; DESCRIBE FORMATTED obs_rc"'
    dx master bash -c "beeline -u jdbc:hive2://master:10000/ghcn -n root --silent=true --outputformat=table -e 'SHOW TABLES; DESCRIBE FORMATTED obs_rc;' 2>/dev/null" | grep -v -E '^\|\s+\|\s+\|' | head -50; } > $T/v02_describe_rc.txt
  { echo '$ docker exec master bash /project/hive/benchmark_hive.sh'; cat $L/hive_benchmark.log; } > $T/v03_benchmark_runs.txt
  { echo '$ cat results/hive_benchmark_summary.csv'; cut -d, -f1,2,4,8,9,10,12,13 results/hive_benchmark_summary.csv | column -t -s,
    echo; echo '$ hdfs dfs -du -s -h <table locations>'; column -t -s, results/hive_storage.csv; } > $T/v04_benchmark_summary.txt
  head -120 $L/hive_query_results.log > $T/v05_query_results.txt
  ;;
mongo)
  { echo '$ docker compose run --rm tools python mongodb/ingest.py'; grep -v -E 'it/s\]$|B/s\]$' $L/mongo_ingest.log | tr '\r' '\n' | grep -v -E '^\s*[0-9]+%|^\S+\.csv\.gz:\s+[0-9]{1,2}%' | tail -30; } > $T/g01_ingest.txt
  { echo '$ docker compose run --rm tools python mongodb/profile_queries.py'; cat $L/mongo_profile.log; } > $T/g02_profile.txt
  { echo '$ Get-Content mongodb\queries.js | docker exec -i mongodb mongosh --quiet ghcn'; section $L/mongo_queries.log '==== Creating indexes' '==== Q1'; } > $T/g03_indexes.txt
  for q in Q1 Q2 Q3 Q4 Q5 Q6 Q7; do
    nxt=$(case $q in Q1) echo '==== Q2';; Q2) echo '==== Q3';; Q3) echo '==== Q4';; Q4) echo '==== Q5';; Q5) echo '==== Q6';; Q6) echo '==== Q7';; Q7) echo '==== explain';; esac)
    section $L/mongo_queries.log "==== $q" "$nxt" > $T/g_$q.txt
  done
  section $L/mongo_queries.log '==== explain' 'zzzz' > $T/g_explain.txt
  { echo '$ docker exec -i mongodb mongoimport --db ghcn --collection stations_import --drop < data/stations.jsonl'; cat $L/mongoimport.log 2>/dev/null; } > $T/g04_mongoimport.txt
  ;;
*) echo "usage: $0 cluster|hdfs|mr|pig|hive|mongo"; exit 1;;
esac
ls -1 $T | wc -l
