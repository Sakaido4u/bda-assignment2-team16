#!/usr/bin/env bash
# Renders *.xml.template -> real Hadoop/Hive config files using environment variables.
# Used by the Docker entrypoint AND by install-native.sh, so both modes share one set of templates.
#   TEMPLATE_DIR   (default /opt/bda/templates)
#   HADOOP_CONF_DIR, HIVE_CONF_DIR must be set.
set -euo pipefail

TEMPLATE_DIR=${TEMPLATE_DIR:-/opt/bda/templates}
export NODE_HOSTNAME=${NODE_HOSTNAME:-$(hostname)}

# Only these variables are substituted; Hadoop's own ${...} expressions stay untouched.
VARS='${MASTER_HOST} ${NODE_HOSTNAME} ${HDFS_REPLICATION} ${HDFS_BLOCK_SIZE}
${YARN_NM_MEMORY_MB} ${YARN_NM_VCORES} ${YARN_MIN_ALLOC_MB} ${YARN_MAX_ALLOC_MB}
${MAP_MEMORY_MB} ${MAP_JAVA_OPTS} ${REDUCE_MEMORY_MB} ${REDUCE_JAVA_OPTS}
${AM_MEMORY_MB} ${AM_JAVA_OPTS}
${METASTORE_DB_HOST} ${METASTORE_DB_NAME} ${METASTORE_DB_USER} ${METASTORE_DB_PASSWORD}'

for t in "$TEMPLATE_DIR"/*.template; do
  name=$(basename "$t" .template)
  if [ "$name" = "hive-site.xml" ]; then dest="$HIVE_CONF_DIR"; else dest="$HADOOP_CONF_DIR"; fi
  envsubst "$VARS" < "$t" > "$dest/$name"
done

# workers file: one hostname per line
echo "${WORKER_HOSTS}" | tr ',' '\n' | sed '/^$/d' > "$HADOOP_CONF_DIR/workers"

echo "[render-config] node=${NODE_HOSTNAME} master=${MASTER_HOST} workers=${WORKER_HOSTS} repl=${HDFS_REPLICATION} block=${HDFS_BLOCK_SIZE}"
