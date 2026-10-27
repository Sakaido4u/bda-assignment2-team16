#!/usr/bin/env bash
# =====================================================================
#  Mode B fallback WITHOUT Docker - Ubuntu 22.04 / 24.04 (bare metal or WSL2)
#  Installs the same versions (JDK 8, Hadoop 3.3.6, Hive 3.1.3, Pig 0.18.0) and renders the
#  SAME config templates as the Docker image (docker/hadoop/templates), driven by .env.
#
#  Usage (from the project folder, on every machine):
#     sudo ./install-native.sh master      # on the master machine
#     sudo ./install-native.sh worker1     # on worker 1
#     sudo ./install-native.sh worker2     # on worker 2
#  Then, on the master only, as the hadoop user:
#     sudo -iu hadoop /opt/bda/native-start.sh
# =====================================================================
set -euo pipefail
ROLE=${1:?usage: sudo ./install-native.sh master|worker1|worker2}
HERE=$(cd "$(dirname "$0")" && pwd)
set -a; . "$HERE/.env"; set +a

HADOOP_VERSION=3.3.6; HIVE_VERSION=3.1.3; PIG_VERSION=0.18.0; PG_JDBC=42.7.4
TARBALLS="$HERE/docker/hadoop/tarballs"
HUSER=hadoop

echo ">>> [1/7] packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-8-jdk-headless openssh-server openssh-client \
  gettext-base netcat-openbsd python3 curl rsync
JAVA_HOME=$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")

echo ">>> [2/7] /etc/hosts entries (from .env)"
sed -i '/# bda16-cluster/d' /etc/hosts
{
  echo "$MASTER_IP  master   # bda16-cluster"
  echo "$WORKER1_IP worker1  # bda16-cluster"
  echo "$WORKER2_IP worker2  # bda16-cluster"
} >> /etc/hosts
# Ubuntu maps its own hostname to 127.0.1.1 - Hadoop daemons would then bind to loopback
sed -i "/^127.0.1.1/d" /etc/hosts
hostnamectl set-hostname "$ROLE" 2>/dev/null || hostname "$ROLE"

echo ">>> [3/7] hadoop user + passwordless SSH"
id -u $HUSER >/dev/null 2>&1 || useradd -m -s /bin/bash $HUSER
sudo -u $HUSER bash -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && [ -f ~/.ssh/id_rsa ] || ssh-keygen -q -t rsa -N "" -f ~/.ssh/id_rsa'
sudo -u $HUSER bash -c 'cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys && sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
printf 'Host master worker1 worker2\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n' > /home/$HUSER/.ssh/config
chown $HUSER:$HUSER /home/$HUSER/.ssh/config
systemctl enable --now ssh 2>/dev/null || service ssh start

echo ">>> [4/7] Hadoop / Hive / Pig binaries"
fetch() {   # file url
  if [ -f "$TARBALLS/$1" ]; then cp "$TARBALLS/$1" /tmp/; else curl -fL --retry 5 -o "/tmp/$1" "$2"; fi
}
mkdir -p /opt
if [ ! -d /opt/hadoop ]; then
  fetch hadoop-$HADOOP_VERSION.tar.gz https://dlcdn.apache.org/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION.tar.gz
  tar -xzf /tmp/hadoop-$HADOOP_VERSION.tar.gz -C /opt && mv /opt/hadoop-$HADOOP_VERSION /opt/hadoop
  rm -rf /opt/hadoop/share/doc
fi
if [ "$ROLE" = master ] && [ ! -d /opt/hive ]; then
  fetch apache-hive-$HIVE_VERSION-bin.tar.gz https://repo.huaweicloud.com/apache/hive/hive-$HIVE_VERSION/apache-hive-$HIVE_VERSION-bin.tar.gz
  tar -xzf /tmp/apache-hive-$HIVE_VERSION-bin.tar.gz -C /opt && mv /opt/apache-hive-$HIVE_VERSION-bin /opt/hive
  rm -f /opt/hive/lib/guava-19.0.jar /opt/hive/lib/log4j-slf4j-impl-*.jar          # Guava + SLF4J conflicts
  cp /opt/hadoop/share/hadoop/common/lib/guava-27.0-jre.jar /opt/hive/lib/
  fetch postgresql-$PG_JDBC.jar https://repo1.maven.org/maven2/org/postgresql/postgresql/$PG_JDBC/postgresql-$PG_JDBC.jar
  cp /tmp/postgresql-$PG_JDBC.jar /opt/hive/lib/
  fetch pig-$PIG_VERSION.tar.gz https://dlcdn.apache.org/pig/pig-$PIG_VERSION/pig-$PIG_VERSION.tar.gz
  tar -xzf /tmp/pig-$PIG_VERSION.tar.gz -C /opt && mv /opt/pig-$PIG_VERSION /opt/pig
fi

echo ">>> [5/7] environment"
cat > /etc/profile.d/bda16.sh <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_HOME=/opt/hadoop HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop HADOOP_MAPRED_HOME=/opt/hadoop
export HIVE_HOME=/opt/hive HIVE_CONF_DIR=/opt/hive/conf PIG_HOME=/opt/pig PIG_CLASSPATH=/opt/hadoop/etc/hadoop
export PATH=\$PATH:/opt/hadoop/bin:/opt/hadoop/sbin:/opt/hive/bin:/opt/pig/bin
EOF
. /etc/profile.d/bda16.sh
echo "export JAVA_HOME=$JAVA_HOME" >> /opt/hadoop/etc/hadoop/hadoop-env.sh

echo ">>> [6/7] render configs from the shared templates"
mkdir -p /opt/bda /hadoop/dfs /hadoop/tmp /opt/hive/conf
cp -r "$HERE/docker/hadoop/templates" /opt/bda/
TEMPLATE_DIR=/opt/bda/templates NODE_HOSTNAME=$ROLE bash "$HERE/docker/hadoop/render-config.sh"
chown -R $HUSER:$HUSER /opt/hadoop /hadoop /opt/bda
[ -d /opt/hive ] && chown -R $HUSER:$HUSER /opt/hive /opt/pig

echo ">>> [7/7] role specific setup"
if [ "$ROLE" = master ]; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql
  sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$METASTORE_DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $METASTORE_DB_USER WITH PASSWORD '$METASTORE_DB_PASSWORD';"
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$METASTORE_DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $METASTORE_DB_NAME OWNER $METASTORE_DB_USER;"
  # Hive must talk to the local PostgreSQL in native mode
  sed -i "s#jdbc:postgresql://[^:]*:5432#jdbc:postgresql://localhost:5432#" /opt/hive/conf/hive-site.xml
  cat > /opt/bda/native-start.sh <<'EOF'
#!/usr/bin/env bash
# start the whole cluster from the master (uses passwordless SSH to the workers)
set -e
. /etc/profile.d/bda16.sh
[ -f /hadoop/dfs/name/current/VERSION ] || hdfs namenode -format -force -nonInteractive -clusterId bda-team16
start-dfs.sh
start-yarn.sh
mapred --daemon start historyserver
hdfs dfsadmin -safemode wait
hdfs dfs -mkdir -p /tmp /tmp/hive /user/hive/warehouse /user/hadoop && hdfs dfs -chmod -R 1777 /tmp
schematool -dbType postgres -info >/dev/null 2>&1 || schematool -dbType postgres -initSchema
nohup hive --service metastore   > /tmp/metastore.log 2>&1 &
sleep 15
nohup hive --service hiveserver2 > /tmp/hiveserver2.log 2>&1 &
hdfs dfsadmin -report | grep -E 'Live datanodes'
yarn node -list
EOF
  chmod +x /opt/bda/native-start.sh
  echo
  echo "Master ready. Copy the hadoop user's public key to each worker:"
  echo "   sudo -iu hadoop ssh-copy-id hadoop@worker1 ; sudo -iu hadoop ssh-copy-id hadoop@worker2"
  echo "Then start everything:  sudo -iu hadoop /opt/bda/native-start.sh"
else
  echo "Worker $ROLE ready. Its daemons are started from the master by start-dfs.sh / start-yarn.sh."
  echo "Make sure the master's /home/hadoop/.ssh/id_rsa.pub is in this machine's /home/hadoop/.ssh/authorized_keys."
fi
