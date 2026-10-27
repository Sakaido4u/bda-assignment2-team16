# Mode B – running the cluster on three real machines

The same image and the same `.env` are used as in Mode A. The service names (`master`, `worker1`, `worker2`, `metastore-db`, `mongodb`) do not change, so no Hadoop/Hive configuration changes either. The containers are attached to a **Docker Swarm overlay network**, which lets them resolve each other by name across machines.

> **Important for Windows laptops.** Docker Desktop runs its engine inside a NATed WSL2 VM. Swarm overlay traffic (UDP 4789 VXLAN, 7946 gossip) between two Docker Desktop hosts often does not get through that NAT. Options, from most to least reliable:
> 1. Boot the three machines into **Ubuntu 22.04** (installed or a live USB with persistence) and install Docker Engine (`curl -fsSL https://get.docker.com | sh`).
> 2. **Windows 11 22H2+:** enable WSL *mirrored networking* (`[wsl2]` → `networkingMode=mirrored` in `.wslconfig`) and run Docker Engine inside Ubuntu-WSL.
> 3. Use the no-Docker fallback `install-native.sh` (section C).

## 0. Fill in `.env` (same file on every machine)

```ini
MASTER_IP=192.168.1.10
WORKER1_IP=192.168.1.11
WORKER2_IP=192.168.1.12
```

On a machine with less RAM, lower `YARN_NM_MEMORY_MB` (each worker offers this much memory to YARN).

## 1. Network checks (PowerShell on every machine)

```powershell
ipconfig                                   # note this machine's IPv4 address
Test-NetConnection 192.168.1.10 -Port 2377 # from each worker to the master (after swarm init)
Test-NetConnection 192.168.1.11 -Port 7946
ping 192.168.1.12
```

### Windows Firewall rules (run as Administrator on each machine)

```powershell
New-NetFirewallRule -DisplayName "BDA16 Swarm mgmt"    -Direction Inbound -Protocol TCP -LocalPort 2377 -Action Allow
New-NetFirewallRule -DisplayName "BDA16 Swarm gossip"  -Direction Inbound -Protocol TCP -LocalPort 7946 -Action Allow
New-NetFirewallRule -DisplayName "BDA16 Swarm gossipU" -Direction Inbound -Protocol UDP -LocalPort 7946 -Action Allow
New-NetFirewallRule -DisplayName "BDA16 Overlay VXLAN" -Direction Inbound -Protocol UDP -LocalPort 4789 -Action Allow
New-NetFirewallRule -DisplayName "BDA16 Hadoop UIs"    -Direction Inbound -Protocol TCP -LocalPort 9870,9864,8088,8042,19888,10000,10002,5000,27017 -Action Allow
# needed for install-native.sh (no Docker) only: Hadoop RPC/data ports
New-NetFirewallRule -DisplayName "BDA16 Hadoop RPC"    -Direction Inbound -Protocol TCP -LocalPort 9000,9866,9867,8030-8033,8040,13562,10020,9083 -Action Allow
```

| Port | Used by |
|---|---|
| 2377/tcp | Swarm cluster management (master) |
| 7946/tcp+udp | Swarm node gossip |
| 4789/udp | overlay network data (VXLAN) |
| 9000 | HDFS NameNode RPC |
| 9866 / 9867 | DataNode data transfer / IPC |
| 9870, 9864 | NameNode / DataNode web UI |
| 8030-8033, 8088 | ResourceManager scheduler/tracker/admin RPC, web UI |
| 8040, 8042, 13562 | NodeManager localizer, web UI, shuffle |
| 10020, 19888 | JobHistory RPC, web UI |
| 9083, 10000, 10002 | Hive Metastore, HiveServer2, HS2 UI |
| 27017, 5000 | MongoDB, dashboard |

## A. Recommended: Swarm overlay + the two compose files

**Master machine**

```bash
docker swarm init --advertise-addr 192.168.1.10
# prints:  docker swarm join --token SWMTKN-... 192.168.1.10:2377
docker network create -d overlay --attachable bda16-overlay
docker compose -f docker-compose.master.yml build          # builds bda16/hadoop and bda16/dashboard
docker save bda16/hadoop:3.3.6 -o bda16-hadoop.tar         # copy this file to the workers (USB / scp)
```

**Each worker machine**

```bash
docker swarm join --token SWMTKN-... 192.168.1.10:2377
docker load -i bda16-hadoop.tar
```

**Start (master first, then the workers)**

```bash
# master
docker compose -f docker-compose.master.yml up -d
# worker 1
WORKER_NAME=worker1 docker compose -f docker-compose.worker.yml up -d
# worker 2   (PowerShell:  $env:WORKER_NAME="worker2"; docker compose -f docker-compose.worker.yml up -d)
WORKER_NAME=worker2 docker compose -f docker-compose.worker.yml up -d
```

**Verify (on the master):** run `docker node ls` (3 nodes Ready), then `docker exec master hdfs dfsadmin -report` (Live datanodes (2)) and `docker exec master yarn node -list` (2 RUNNING). Everything else (`hdfs-operations.sh`, `run-jobs.sh`, `run-pig.sh`, Hive, MongoDB, dashboard) runs exactly as in Mode A.

## B. Alternative: one Swarm stack with node labels

```bash
# on the master, after all three nodes have joined
docker node ls
docker node update --label-add role=master  <master-hostname>
docker node update --label-add role=worker1 <worker1-hostname>
docker node update --label-add role=worker2 <worker2-hostname>
set -a; . ./.env; set +a
docker stack deploy -c docker-stack.yml bda16
docker stack ps bda16            # each service shows the node it was placed on
```

`docker stack` cannot build images, so load `bda16-hadoop.tar` on every node first, or push the image to a registry.

## C. Fallback without Docker (Ubuntu 22.04 / WSL2)

```bash
# every machine, from the project folder (tarballs in docker/hadoop/tarballs are reused if present)
sudo ./install-native.sh master      # or worker1 / worker2
# on the master: give the hadoop user passwordless SSH to the workers
sudo -iu hadoop ssh-copy-id hadoop@worker1
sudo -iu hadoop ssh-copy-id hadoop@worker2
sudo -iu hadoop /opt/bda/native-start.sh
```

The script:
- writes these lines to `/etc/hosts`:
  ```
  192.168.1.10 master
  192.168.1.11 worker1
  192.168.1.12 worker2
  ```
- removes Ubuntu's `127.0.1.1 <hostname>` line, which would make the daemons bind to loopback
- creates the `hadoop` user and its SSH key
- installs JDK 8, Hadoop 3.3.6, Hive 3.1.3 (with the guava fix) and Pig 0.18.0
- renders the same XML templates
- writes `etc/hadoop/workers` (worker1, worker2)
- on the master, installs PostgreSQL for the metastore

`native-start.sh` formats the NameNode on first run, then runs `start-dfs.sh`, `start-yarn.sh` and the JobHistory server, initialises the metastore schema, and starts the Metastore and HiveServer2.
