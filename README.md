# BDA Assignment 2 – Track B – Team 16

**Distributed Big Data Analytics of NOAA GHCN-Daily Climate Records using MongoDB, Hadoop MapReduce, Apache Pig and Apache Hive on a Multi-Node Cluster**

BCS714D · JSS Academy of Technical Education, Bengaluru · Faculty: Ms. Sandhiya B
Team: Deeptanshu Pandey (1JS23CS044) · Chirag S (1JS23CS039) · Gagan Surendra Shamnur (1JS23CS052)

The write-up is assembled from the sections in `report/parts/`. Screenshots are in `report/screenshots/` and architecture diagrams in `report/diagrams/`.

---

## 1. What is in this folder

| Path | Contents |
|---|---|
| `.env.example` | copy to `.env` and set `METASTORE_DB_PASSWORD`; `.env` is **the only file to edit** – hostnames/IPs, HDFS block size, YARN memory, years to download |
| `docker/hadoop/` | one image (Temurin JDK 8 + Hadoop 3.3.6 + Hive 3.1.3 + Pig 0.18.0); `NODE_ROLE=master\|worker` picks the daemons; XML configs are rendered from `templates/` |
| `docker-compose.yml` | **Mode A** – master + worker1 + worker2 + PostgreSQL + MongoDB + dashboard on one laptop |
| `docker-compose.master.yml`, `docker-compose.worker.yml`, `docker-stack.yml` | **Mode B** – three real machines via a Docker Swarm overlay network |
| `install-native.sh` | Mode B without Docker (Ubuntu / WSL2), same versions and templates |
| `scripts/` | start / stop / reset / status, data download, station conversion, HDFS demo, charts |
| `mapreduce/` | Java MapReduce (Maven), Python Streaming, `run-jobs.sh`, sample outputs |
| `pig/`, `hive/` | Pig cleaning, Hive DDL, benchmark queries and `benchmark_hive.sh` |
| `mongodb/` | `ingest.py`, `queries.js`, `profile_queries.py`, `build_summaries.py` |
| `dashboard/` | Part 2 Flask dashboard (`app.py`, `templates/`, `static/`, `Dockerfile`) |
| `results/` | every measured number (CSV/JSON), logs and charts |
| `report/` | report sections, screenshots, diagrams, build tools, Mode B guide |

## 2. Prerequisites (Windows 10/11)

1. **Docker Desktop** 4.x with the WSL2 backend.
2. Give the WSL2 VM 8 GB RAM. Create `C:\Users\<you>\.wslconfig`:
   ```ini
   [wsl2]
   memory=8GB
   processors=4
   swap=4GB
   ```
   Then run `wsl --shutdown` in PowerShell and restart Docker Desktop. Check it with `docker info` (look for `Total Memory: ~7.7GiB`).
3. About **25 GB** of free disk: images 3 GB, raw data 0.5 GB compressed, HDFS 2 × (3.8 GB raw + 3.9 GB clean + RCFile/ORC copies), MongoDB 2 GB.
4. Git (optional). `.gitattributes` forces LF line endings for `*.sh *.xml *.pig *.hql *.py`. CRLF endings break bash inside Linux containers (`$'\r': command not found`). The Dockerfile also strips `\r` from its own scripts as a safety net.

| Software | Version | Why this version |
|---|---|---|
| JDK | Eclipse Temurin 8 (jammy) | Hive 3.1.x supports Java 8 only |
| Hadoop | 3.3.6 | latest 3.3 line; verified with Hive 3.1.3 |
| Hive | 3.1.3 | needs **guava-27** from Hadoop in place of its own guava-19 (handled in the Dockerfile) |
| Pig | 0.18.0 | first Pig release built for Hadoop 3 (0.17 needs patches); MapReduce mode |
| PostgreSQL | 15.8 | Hive metastore DB |
| MongoDB | 7.0.14 | WiredTiger cache capped at 0.5 GB for the laptop |
| Python | 3.12 (dashboard/tools image), 3.10 (streaming on workers) | |

## 3. Run everything (Mode A, one laptop)

```powershell
cd bda-assignment2-team16
copy .env.example .env               # once: then set METASTORE_DB_PASSWORD in .env
.\scripts\fetch-tarballs.ps1         # once: Hadoop/Hive/Pig tarballs (~1.5 GB)
.\scripts\start-cluster.ps1          # builds images first time, formats NameNode only once,
                                     # waits for 2 live DataNodes + 2 NodeManagers
.\scripts\cluster-status.ps1         # dfsadmin -report, yarn node -list, jps on each node
.\scripts\download-data.ps1          # NOAA files (default 2023-2025) + stations CSV/TSV/JSON

# Theme 2 - HDFS + MapReduce
docker exec master bash /project/scripts/hdfs-operations.sh
.\mapreduce\build.ps1                # Maven inside a container -> mapreduce\target\ghcn-mapreduce.jar
docker exec master bash /project/mapreduce/run-jobs.sh

# Theme 3 - Pig + Hive
docker exec master bash /project/pig/run-pig.sh
docker exec master bash -c "beeline -u jdbc:hive2://master:10000 -n root -f /project/hive/01_create_tables.hql"
docker exec master bash -c "beeline -u jdbc:hive2://master:10000 -n root -f /project/hive/02_bonus_tables.hql"
docker exec master bash /project/hive/benchmark_hive.sh

# Theme 1 - MongoDB
docker compose run --rm tools python mongodb/ingest.py
docker compose run --rm tools python mongodb/profile_queries.py     # before/after indexes
docker cp mongodb\queries.js mongodb:/tmp/queries.js; docker exec mongodb mongosh --quiet ghcn /tmp/queries.js
docker compose run --rm tools python mongodb/build_summaries.py     # for the dashboard

# Charts + Part 2 dashboard
docker compose run --rm tools python scripts/make_charts.py
start http://localhost:5000
```

Other commands: `.\scripts\stop-cluster.ps1` stops the cluster and keeps the data. `.\scripts\reset-cluster.ps1` deletes all volumes and asks for confirmation first.

### Web UIs

| UI | URL |
|---|---|
| NameNode | http://localhost:9870 |
| ResourceManager | http://localhost:8088 |
| JobHistory | http://localhost:19888 |
| DataNode worker1 / worker2 | http://localhost:9864 · http://localhost:9865 |
| NodeManager worker1 / worker2 | http://localhost:8042 · http://localhost:8043 |
| HiveServer2 | http://localhost:10002 |
| Dashboard | http://localhost:5000 |

Links inside the Hadoop UIs point to `worker1:8042` and similar container names. To make them clickable from Windows, add `127.0.0.1 master worker1 worker2` to `C:\Windows\System32\drivers\etc\hosts`. This is optional.

## 4. Proving to the examiner that 3 nodes work together

1. `.\scripts\cluster-status.ps1` should show **Live datanodes (2)**, **Total Nodes:2** (both RUNNING), and NameNode/RM on master with DataNode/NodeManager on each worker (`jps`).
2. NameNode UI → *Datanodes* tab: worker1 and worker2 both *In Service*, with similar block counts.
3. NameNode UI → *Utilities → Browse the file system* → `/ghcn/raw/2025.csv`. Every block lists **two** locations, worker1 and worker2. On the command line: `hdfs fsck /ghcn -files -blocks -locations` (see `results/logs/hdfs_operations.log`).
4. ResourceManager UI → *Nodes*: 2 active NodeManagers. While a job runs, both show running containers.
5. JobHistory → job → *Map tasks* → *Successful attempts*: the **Node** column alternates between worker1 and worker2. `results/mr_task_nodes.csv` has the same data from the REST API.
6. Dashboard → *Cluster* page: live view of all of the above.
7. Fault-tolerance demo: `docker stop worker2`. HDFS still serves every file because each block has a second replica on worker1. `docker start worker2` brings it back.

## 5. Common errors and fixes

| Symptom | Cause / fix |
|---|---|
| `$'\r': command not found` in a container | CRLF line endings. Re-checkout with `.gitattributes`, or `dos2unix` the file |
| Only 1 live DataNode after a reset | an old DataNode volume has a different clusterID. Run `.\scripts\reset-cluster.ps1` (wipes volumes) |
| Jobs stuck in ACCEPTED | not enough YARN memory. Close other apps, check `.wslconfig`, or lower `MAP_MEMORY_MB` in `.env` |
| NodeManager UNHEALTHY | Docker disk > 98.5 % full. Run `docker system prune` |
| `NoSuchMethodError com.google.common.base.Preconditions` in Hive | Guava conflict. The image replaces guava-19 with guava-27 |
| Beeline `Connection refused` right after start | HiveServer2 takes about 60 s to open port 10000 |
| `archive.apache.org` download at a few KB/s | it is throttled. `fetch-tarballs.ps1` uses the CDN and a mirror |
| Git Bash mangles `/project/...` paths in `docker exec` | use PowerShell, or prefix with `MSYS_NO_PATHCONV=1` |
| Port already in use | change the left-hand port in `docker-compose.yml` |
| Restarting the dashboard also restarted `master` and killed a running job | after editing `.env`, `docker compose up -d dashboard` recreates its dependencies too. Use `docker compose up -d --no-deps dashboard` |
| `dfsadmin` shows under-replicated blocks after jobs | job jars default to replication 10. The template now sets `mapreduce.client.submit.file.replication=${HDFS_REPLICATION}`; for old files run `hdfs dfs -setrep -R 2 /tmp` |
| MongoDB ingestion fails with `Cannot allocate memory` | don't run it while Hive/Pig jobs fill YARN; run phases one after another on an 8 GB VM |
