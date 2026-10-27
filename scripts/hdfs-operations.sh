#!/usr/bin/env bash
# Theme 2 - HDFS file management. Runs INSIDE the master container:
#   docker exec master bash /project/scripts/hdfs-operations.sh
# Every command is echoed with an explanation; the full transcript goes to results/logs/hdfs_operations.log
set -uo pipefail
cd /project
LOG=results/logs/hdfs_operations.log
mkdir -p results/logs
exec > >(tee "$LOG") 2>&1

step() { echo; echo "================================================================"; echo "## $1"; echo "================================================================"; }
run()  { echo "\$ $*"; eval "$@" 2>&1 | grep -v -E 'WARN (util.NativeCodeLoader|sasl)|Unable to write to output stream'; }

step "1. Create the project directory tree in HDFS"
run "hdfs dfs -mkdir -p /ghcn/raw /ghcn/stations /ghcn/countries /ghcn/output"

step "2. Upload the raw yearly files (decompressed on the fly so HDFS can split them into 32 MB blocks)"
for f in data/raw/[12][0-9][0-9][0-9].csv.gz; do
  y=$(basename "$f" .csv.gz)
  if hdfs dfs -test -e /ghcn/raw/$y.csv 2>/dev/null; then
    echo "/ghcn/raw/$y.csv already present - skipping upload"
  else
    run "zcat $f | hdfs dfs -put - /ghcn/raw/$y.csv"
  fi
done

step "3. Upload station and country metadata"
run "hdfs dfs -put -f data/stations.tsv /ghcn/stations/stations.tsv"
run "hdfs dfs -put -f data/countries.tsv /ghcn/countries/countries.tsv"

step "4. List everything recursively"
run "hdfs dfs -ls -R /ghcn"

step "5. Space used (logical size, then size including both replicas)"
run "hdfs dfs -du -h /ghcn"
run "hdfs dfs -du -s -h /ghcn/raw"

step "6. Peek at the data without downloading it"
LATEST=$(hdfs dfs -ls /ghcn/raw 2>/dev/null | awk '{print $NF}' | grep csv | sort | tail -1)
run "hdfs dfs -cat $LATEST | head -n 5"
run "hdfs dfs -cat /ghcn/stations/stations.tsv | head -n 5"

step "7. Copy a file from HDFS back to the local filesystem"
run "rm -f /tmp/stations_copy.tsv && hdfs dfs -get /ghcn/stations/stations.tsv /tmp/stations_copy.tsv"
run "ls -lh /tmp/stations_copy.tsv && wc -l /tmp/stations_copy.tsv"

step "8. Create and remove a temporary directory"
run "hdfs dfs -mkdir -p /ghcn/tmp_demo && hdfs dfs -cp /ghcn/countries/countries.tsv /ghcn/tmp_demo/"
run "hdfs dfs -ls /ghcn/tmp_demo"
run "hdfs dfs -rm -r -skipTrash /ghcn/tmp_demo"

step "9. Replication factor and block size of a raw file"
run "hdfs dfs -stat 'name=%n replication=%r blocksize=%o size=%b' $LATEST"

step "10. fsck: prove every block has 2 replicas, one on worker1 and one on worker2"
run "hdfs fsck $LATEST -files -blocks -locations | head -n 25"
hdfs fsck /ghcn -files -blocks -locations > results/logs/fsck_ghcn_full.log 2>/dev/null
echo "(full fsck report for /ghcn saved to results/logs/fsck_ghcn_full.log)"
run "hdfs fsck /ghcn | sed -n '/^Status/,/Blocks queued/p'"

step "11. Block replicas per DataNode (parsed from fsck)"
echo "replicas  datanode"
grep -o 'DatanodeInfoWithStorage\[[0-9.]*' results/logs/fsck_ghcn_full.log | sed 's/DatanodeInfoWithStorage\[//' \
  | sort | uniq -c | while read -r n ip; do echo "$n  $ip ($(getent hosts "$ip" | awk '{print $2}'))"; done

step "12. DataNode report"
run "hdfs dfsadmin -report | grep -E 'Live datanodes|^Name:|^Hostname:|^DFS Used:|Num of Blocks'"
echo; echo "HDFS operations finished."
