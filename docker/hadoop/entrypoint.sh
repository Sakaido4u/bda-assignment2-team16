#!/usr/bin/env bash
# Starts the right Hadoop/Hive daemons for this node.
#   NODE_ROLE=master -> NameNode, SecondaryNameNode, ResourceManager, JobHistory, Hive Metastore, HiveServer2
#   NODE_ROLE=worker -> DataNode, NodeManager
set -euo pipefail

/opt/bda/render-config.sh

log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

wait_for_port() {   # host port label
  local tries=0
  until nc -z "$1" "$2" 2>/dev/null; do
    tries=$((tries+1)); [ $tries -gt 120 ] && { log "timeout waiting for $3 ($1:$2)"; return 1; }
    sleep 2
  done
  log "$3 is reachable at $1:$2"
}

heap() { export HADOOP_HEAPSIZE_MAX="$1"; }

stop_all() {
  log "stopping daemons..."
  if [ "$NODE_ROLE" = "master" ]; then
    pkill -f HiveServer2 || true; pkill -f HiveMetaStore || true
    mapred --daemon stop historyserver || true
    yarn --daemon stop resourcemanager || true
    hdfs --daemon stop secondarynamenode || true
    hdfs --daemon stop namenode || true
  else
    yarn --daemon stop nodemanager || true
    hdfs --daemon stop datanode || true
  fi
  exit 0
}
trap stop_all SIGTERM SIGINT

D=${HADOOP_DAEMON_HEAP_MB}m

if [ "$NODE_ROLE" = "master" ]; then
  # ---- format the NameNode only on the very first start (empty volume) ----
  if [ ! -f /hadoop/dfs/name/current/VERSION ]; then
    log "first start: formatting NameNode"
    hdfs namenode -format -force -nonInteractive -clusterId bda-team16
  else
    log "NameNode already formatted - keeping existing HDFS metadata"
  fi

  heap $D;     hdfs --daemon start namenode
  heap 256m;   hdfs --daemon start secondarynamenode
  heap $D;     yarn --daemon start resourcemanager
  heap 256m;   mapred --daemon start historyserver
  unset HADOOP_HEAPSIZE_MAX

  hdfs dfsadmin -safemode wait
  hdfs dfs -mkdir -p /tmp /tmp/hive /tmp/logs /user/root /user/hive/warehouse /mr-history
  hdfs dfs -chmod -R 1777 /tmp
  hdfs dfs -chmod 777 /user/hive/warehouse
  log "HDFS base directories ready"

  # ---- Hive: metastore schema in PostgreSQL, then Metastore + HiveServer2 ----
  wait_for_port "$METASTORE_DB_HOST" 5432 "PostgreSQL metastore DB"
  if schematool -dbType postgres -info >/dev/null 2>&1; then
    log "Hive metastore schema already present"
  else
    log "initialising Hive metastore schema"
    schematool -dbType postgres -initSchema
  fi
  heap 512m; nohup hive --service metastore   > /var/log/hive/metastore.log 2>&1 &
  wait_for_port localhost 9083 "Hive Metastore"
  heap 1024m; nohup hive --service hiveserver2 > /var/log/hive/hiveserver2.log 2>&1 &
  unset HADOOP_HEAPSIZE_MAX
  log "master services launched (HiveServer2 needs ~60s to open port 10000)"
else
  wait_for_port "$MASTER_HOST" 9000 "NameNode RPC"
  heap $D; hdfs --daemon start datanode
  heap $D; yarn --daemon start nodemanager
  unset HADOOP_HEAPSIZE_MAX
  log "worker services launched on ${NODE_HOSTNAME}"
fi

# keep the container in the foreground and stream daemon logs to `docker logs`
touch /var/log/hive/keepalive.log
tail -n 0 -F "$HADOOP_HOME"/logs/*.log /var/log/hive/*.log &
wait $!
