# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# One image for every cluster node. NODE_ROLE=master|worker picks the daemons.
#   Hadoop 3.3.6  +  Hive 3.1.3  +  Pig 0.18.0  on  Eclipse Temurin JDK 8
# Tarballs are fetched once by scripts/fetch-tarballs.ps1 into ./tarballs and
# bind-mounted during the build (no copy left inside the image layers).
# ---------------------------------------------------------------------------
FROM eclipse-temurin:8-jdk-jammy

ARG HADOOP_VERSION=3.3.6
ARG HIVE_VERSION=3.1.3
ARG PIG_VERSION=0.18.0
ARG PG_JDBC_VERSION=42.7.4

ENV HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop \
    HADOOP_MAPRED_HOME=/opt/hadoop \
    HIVE_HOME=/opt/hive \
    HIVE_CONF_DIR=/opt/hive/conf \
    PIG_HOME=/opt/pig \
    PIG_CLASSPATH=/opt/hadoop/etc/hadoop
ENV PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$HIVE_HOME/bin:$PIG_HOME/bin:$PATH

# Hadoop 3 refuses to start daemons as root unless these are set explicitly.
ENV HDFS_NAMENODE_USER=root HDFS_DATANODE_USER=root HDFS_SECONDARYNAMENODE_USER=root \
    YARN_RESOURCEMANAGER_USER=root YARN_NODEMANAGER_USER=root MAPRED_HISTORYSERVER_USER=root

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      gettext-base procps netcat-openbsd python3 curl less ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN --mount=type=bind,source=tarballs,target=/tarballs \
    set -eux; \
    tar -xzf /tarballs/hadoop-${HADOOP_VERSION}.tar.gz -C /opt; \
    mv /opt/hadoop-${HADOOP_VERSION} ${HADOOP_HOME}; \
    rm -rf ${HADOOP_HOME}/share/doc ${HADOOP_HOME}/share/hadoop/*/sources ${HADOOP_HOME}/share/hadoop/*/jdiff; \
    tar -xzf /tarballs/apache-hive-${HIVE_VERSION}-bin.tar.gz -C /opt; \
    mv /opt/apache-hive-${HIVE_VERSION}-bin ${HIVE_HOME}; \
    # --- Guava conflict: Hive 3.1.3 ships guava-19, Hadoop 3.3.6 needs guava-27 ---
    rm -f ${HIVE_HOME}/lib/guava-19.0.jar; \
    cp ${HADOOP_HOME}/share/hadoop/common/lib/guava-27.0-jre.jar ${HIVE_HOME}/lib/; \
    # --- duplicate SLF4J binding (harmless warning spam) ---
    rm -f ${HIVE_HOME}/lib/log4j-slf4j-impl-*.jar; \
    cp /tarballs/postgresql-${PG_JDBC_VERSION}.jar ${HIVE_HOME}/lib/; \
    tar -xzf /tarballs/pig-${PIG_VERSION}.tar.gz -C /opt; \
    mv /opt/pig-${PIG_VERSION} ${PIG_HOME}; \
    mkdir -p /hadoop/dfs/name /hadoop/dfs/data /hadoop/tmp /var/log/hive

COPY templates/ /opt/bda/templates/
COPY render-config.sh entrypoint.sh /opt/bda/
RUN sed -i 's/\r$//' /opt/bda/*.sh && chmod +x /opt/bda/*.sh

# Defaults (overridden by .env through docker compose)
ENV NODE_ROLE=worker MASTER_HOST=master WORKER_HOSTS=worker1,worker2 \
    HDFS_REPLICATION=2 HDFS_BLOCK_SIZE=33554432 \
    YARN_NM_MEMORY_MB=1536 YARN_NM_VCORES=3 YARN_MIN_ALLOC_MB=256 YARN_MAX_ALLOC_MB=1536 \
    MAP_MEMORY_MB=512 MAP_JAVA_OPTS=-Xmx400m REDUCE_MEMORY_MB=512 REDUCE_JAVA_OPTS=-Xmx400m \
    AM_MEMORY_MB=512 AM_JAVA_OPTS=-Xmx400m HADOOP_DAEMON_HEAP_MB=384 \
    METASTORE_DB_HOST=metastore-db METASTORE_DB_NAME=metastore \
    METASTORE_DB_USER=hive METASTORE_DB_PASSWORD=hive

WORKDIR /project
ENTRYPOINT ["/opt/bda/entrypoint.sh"]
