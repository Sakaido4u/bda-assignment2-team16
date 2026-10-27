### 5.2 Theme 2 – Hadoop File Management and MapReduce

#### 5.2.1 HDFS file management

`scripts/hdfs-operations.sh` runs every command below inside the master container. It echoes each command and writes the full transcript to `results/logs/hdfs_operations.log` (Fig. A14–A20).

| Step | Command | Result |
|---|---|---|
| Create tree | `hdfs dfs -mkdir -p /ghcn/raw /ghcn/stations /ghcn/countries /ghcn/output` | directories created |
| Upload | `zcat data/raw/YYYY.csv.gz \| hdfs dfs -put - /ghcn/raw/YYYY.csv` | 3 files, 1.38 + 1.38 + 1.31 GB. Decompressed while streaming, because gzip is not splittable: a `.gz` file would give one mapper per file |
| Upload metadata | `hdfs dfs -put -f data/stations.tsv …`, `countries.tsv` | 9.2 MB + 3.4 KB |
| List | `hdfs dfs -ls -R /ghcn` | all files with replication `2` |
| Space | `hdfs dfs -du -h /ghcn` | `/ghcn/raw 3.8 G 7.6 G`: logical size, then size including both replicas |
| Read | `hdfs dfs -cat /ghcn/raw/2025.csv \| head -n 5` | first records streamed from the DataNodes |
| Download | `hdfs dfs -get /ghcn/stations/stations.tsv /tmp/…` | 133,039 lines |
| Copy / delete | `hdfs dfs -cp …`, `hdfs dfs -rm -r -skipTrash /ghcn/tmp_demo` | `Deleted /ghcn/tmp_demo` |
| File metadata | `hdfs dfs -stat 'replication=%r blocksize=%o size=%b'` | `replication=2 blocksize=33554432 size=1310928099` |
| Block report | `hdfs fsck /ghcn -files -blocks -locations` | **126 blocks, 0 under-replicated, average replication 2.0, status HEALTHY** |

**Replication proof.** `2025.csv` is split into 40 blocks, and each block lists `Live_repl=2` with one location on `172.19.0.6` (worker1) and one on `172.19.0.7` (worker2). Counting the locations in the full fsck report gives **126 replicas on worker1 and 126 on worker2**. The DataNode report agrees: 3.83 GB and 3.86 GB used. The NameNode file browser shows the same thing graphically: *Block 0 → Availability: worker1, worker2* (Fig. A20). With replication 2 on two DataNodes, the placement policy must put one copy on each node. Either worker can therefore fail without data loss.

#### 5.2.2 MapReduce in Java

The Maven project (`mapreduce/pom.xml`, `hadoop-client 3.3.6` with *provided* scope) is built inside a `maven:3.9.9-eclipse-temurin-8` container by `mapreduce/build.ps1`, so no JDK or Maven is needed on Windows. The resulting 15.7 KB jar holds two jobs selected by the first argument:

| Class | Role |
|---|---|
| `GhcnRecord` | parses one CSV line; `Quality` enum = custom counters (VALID, MALFORMED, QC_FAILED, MISSING_VALUE, OTHER_ELEMENT) |
| `TempStatsWritable` | **custom `Writable`** holding `tmaxSum, tmaxCount, tminSum, tminCount` (4 longs) |
| `CountryYearTemperature` | **Job 1**: Mapper → key `country \t year`, value = one reading. A **Combiner** merges partial sums. The Reducer outputs avg TMAX, avg TMIN (°C) and counts |
| `ExtremePrecipitation` | **Job 2**: emits `(station, 1)` for PRCP ≥ 50 mm (`-D ghcn.prcp.threshold=500`); `IntSumReducer` as combiner and reducer; extra counters EXTREME_DAYS, PRCP_READINGS |
| `GhcnJobs` | `ToolRunner` driver (`hadoop jar ghcn-mapreduce.jar country-temp|extreme-precip [-D …] in out`) |

**Why a custom Writable?** An average is not associative: the average of averages is wrong when groups have different sizes. Sums and counts *are* associative and commutative, so the same `merge()` can run in the Combiner on each mapper and again in the Reducer. Only the reducer divides.

**Results on YARN** (input `/ghcn/raw`, 3 files, 4.07 GB, 113.1 M records; `results/mapreduce_times.csv`; Fig. A22–A35):

| Metric | Job 1 Java | Job 2 Java | Job 1 Python Streaming |
|---|---|---|---|
| Map tasks / reduce tasks | 122 / 2 | 122 / 2 | 122 / 2 |
| Data-local map tasks | 122 (100 %) | 122 (100 %) | – |
| Wall time | **208.9 s** | 190.4 s | **290.6 s** |
| Map output records | 26,197,386 | 200,298 | 26,197,386 |
| Combine output records | **20,762** | 178,571 | 20,762 |
| Reduce shuffle bytes | 873 KB | 3.2 MB | 556 KB |
| Output records | 560 (country-year rows) | 34,460 (stations) | 560 |
| Counters | VALID 26,197,386 · QC_FAILED 43,210 · OTHER_ELEMENT 86,894,928 · MALFORMED 0 | VALID 33,725,626 · QC_FAILED 25,187 · EXTREME_DAYS 200,298 | QC_FAILED via `reporter:counter` |
| Tasks on worker1 / worker2 | 49 + 1 R / 73 + 1 R | 67 + 2 R / 55 | 54 / 68 + 2 R |

The **Combiner** reduced Job 1's 26.2 million map outputs to only 20,762 records, a **1,262× reduction** of the data shuffled across the network. That is why both reducers finished in seconds. In Job 2 the combiner helps much less (200,298 → 178,571), because the keys are station ids and an extreme-rain day at a given station rarely appears twice within one 32 MB split.

**MALFORMED = 0** shows that every one of the 113 M lines matched the documented 8-field format. The counters also reconcile with the dataset profile: VALID + QC_FAILED + OTHER_ELEMENT = 113,135,524 = all records.

**Sample results** (`mapreduce/sample-output/`):

| Country | Year | avg TMAX °C | avg TMIN °C | TMAX readings |
|---|---|---|---|---|
| India (IN) | 2023 | 32.22 | 20.74 | 30,621 |
| India (IN) | 2024 | 32.30 | 21.18 | 28,080 |
| India (IN) | 2025 | 31.55 | 22.17 | 27,999 |
| Thailand (TH) | 2025 | 33.45 | 23.44 | 10,704 |
| Mauritania (MU) | 2025 | 33.56 | 23.48 | 6,097 |
| Canada (CA) | 2025 | 8.53 | −1.53 | 363,780 |
| Antarctica (AY) | 2025 | −10.47 | −15.20 | 13,859 |

Among countries with more than 5,000 TMAX readings in 2025, the hottest by average daily maximum were Mauritania (33.6 °C), Thailand (33.5 °C), Indonesia and India (31.6 °C). Antarctica was the coldest (−10.5 °C).

The stations with the most days of ≥ 50 mm rain in 2023–2025 were Main Bay, Alaska (114 days), Little Port Walter, Alaska (110), Swift Creek (108), Osmany Intl., Bangladesh (93) and Kosrae, Micronesia (90). **Mahabaleshwar, India** (Western Ghats) is 8th with 85 extreme-rain days.

![Fig. R1: hottest countries (MapReduce Job 1)](../results/charts/mr_hottest_countries.png)

#### 5.2.3 MapReduce with Python Streaming

`mapreduce/streaming/mapper.py`, `combiner.py` and `reducer.py` implement the same Job 1 logic over stdin/stdout. Partial sums travel as text `"sum,count,sum,count"`, and counters use the `reporter:counter:` stderr protocol. The job ran with the same 122 maps and 2 reducers, plus a combiner. Its output was compared row by row with the Java output: **all 560 rows agree**. One value differs in the second decimal (29.53 vs 29.52) because Java's `String.format` rounds half-up while Python rounds the binary floating-point value. This is a printing difference, not a computation difference. Streaming took **290.6 s vs 208.9 s for Java (+39 %)**. Section 6.3 discusses why.

#### 5.2.4 Monitoring on YARN

Every job appears in the ResourceManager UI (`/cluster/apps`) and, after completion, in the JobHistory UI (Fig. A28–A35). The *Successful map attempts* page has a **Node** column that alternates between `/default-rack/worker1:8042` and `/default-rack/worker2:8042`. `mapreduce/task_nodes.py` collects the same information from the JobHistory REST API (`/ws/v1/history/mapreduce/jobs/{id}/tasks/{task}/attempts`) into `results/mr_task_nodes.csv`:

![Fig. R2: tasks per worker](../results/charts/mr_task_nodes.png)

The split is not exactly 50/50 (e.g. 49/73). YARN hands containers to whichever NodeManager heartbeats with free capacity, and the node that hosts the ApplicationMaster has one fewer free container. Both workers nevertheless take part in every job.
