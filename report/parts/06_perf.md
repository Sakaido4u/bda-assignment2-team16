## 6. Performance Evaluation

All measurements were taken on one laptop (8 logical CPUs, 16 GB RAM, of which 7.66 GiB were given to the WSL2 VM running Docker). The three Hadoop containers and MongoDB share those resources. Absolute times would therefore be lower on three real machines, but the *relative* comparisons below hold.

### 6.1 MongoDB – with and without indexes

The full table is in Section 5.1.5 (`results/mongo_profile.csv`). In short:

| Query class | Example | Plan change | Time change |
|---|---|---|---|
| highly selective (≤ 0.01 % of docs) | one station, one station + date range | COLLSCAN → IXSCAN, docs examined 20.4 M → 87–1,053 | **10 s → 4–6 ms (≈ 2,000×)** |
| geospatial | stations within 200 km of Bengaluru | COLLSCAN → 2dsphere IXSCAN, 133,039 → 407 docs | 136 ms → 3 ms (42×) |
| moderately selective (0.6 %) | `^IN` station prefix | COLLSCAN → IXSCAN, 128 k docs | 13.0 s → 2.1 s (6×) |
| low selectivity (64 %) | `readings.element = TMAX` (multikey) | COLLSCAN → IXSCAN, 13.1 M docs | 17.1 s → **30.3 s (slower)** |
| whole-collection aggregation | yearly averages per country | COLLSCAN both times | ≈ 60 s both times |

Rule of thumb from our data: an index pays off when it narrows the scan to a small fraction of the collection. Above roughly 20–30 % selectivity, a sequential collection scan is cheaper than millions of random index lookups. The cost is 568 MB of extra index space and slower inserts (every insert must update all three indexes).

### 6.2 Hive – TEXTFILE vs RCFile

#### 6.2.1 Query time and data read

Average of 3 runs per table (`results/hive_benchmark_summary.csv`, Fig. A46–A47):

| Query | TEXTFILE time (s) | RCFile time (s) | **Speed-up** | TEXTFILE HDFS read (MB) | RCFile HDFS read (MB) | **Read reduction** | Map tasks T / R |
|---|---|---|---|---|---|---|---|
| Q1 full-scan aggregate (2 cols) | 103.7 (97–108) | 78.4 (75–81) | **1.32×** | 3,368 | 1,020 | **−69.7 %** | 14 / 12 |
| Q2 `SELECT *` filter (10 cols) | 75.5 (68–83) | 75.1 (74–77) | **1.01×** | 3,368 | 2,903 | −13.8 % | 14 / 12 |
| Q3 GROUP BY country, year (4 cols) | 111.5 (98–126) | 79.8 (78–82) | **1.40×** | 3,368 | 1,435 | −57.4 % | 14 / 12 |
| Q4 2 of 10 columns | 90.0 (85–94) | 69.1 (68–71) | **1.30×** | 3,368 | 938 | **−72.2 %** | 14 / 12 |
| Q5 join with stations (4 cols) | 142.7 (118–177) | 112.5 (109–114) | **1.27×** | 3,368 | 2,097 | −37.8 % | 15 / 13 |
| **Total, 5 queries** | **523.4** | **414.8** | **1.26×** | 16,840 | 8,393 | **−50.2 %** | |

![Fig. R7: Hive query time](../results/charts/hive_query_time.png)
![Fig. R8: HDFS bytes read per query](../results/charts/hive_hdfs_read.png)

**Bonus formats, 1 run each** (clearly an extra, outside the required comparison):

| Query | RCFile + Snappy (s / MB read) | ORC + ZLIB (s / MB read) |
|---|---|---|
| Q1 | 42.0 s / 184 MB | 26.1 s / 121 MB |
| Q2 | 68.6 s / 526 MB | 21.6 s / 235 MB |
| Q3 | 53.3 s / 205 MB | 25.8 s / 122 MB |
| Q4 | 41.0 s / 153 MB | 24.4 s / 108 MB |
| Q5 | 78.6 s / 437 MB | 51.8 s / 202 MB |
| total | 283.5 s (1.85× faster than TEXTFILE) | 149.7 s (3.50× faster) |

#### 6.2.2 Storage and compression ratio

Measured with `hdfs dfs -du -s` (`results/hive_storage.csv`, Fig. R9):

| Table | Size (one replica) | With 2 replicas | Ratio to TEXTFILE | Compression ratio |
|---|---|---|---|---|
| obs_text (TEXTFILE) | 3,531.4 MB | 7,062.8 MB | 1.00 | 1.00 : 1 |
| **obs_rc (RCFile)** | **3,034.3 MB** | 6,068.5 MB | **0.86** | **1.16 : 1** |
| obs_rc_snappy (bonus) | 551.4 MB | 1,102.7 MB | 0.156 | 6.40 : 1 |
| obs_orc (bonus) | 247.2 MB | 494.4 MB | 0.070 | 14.28 : 1 |

![Fig. R9: Hive storage by format](../results/charts/hive_storage.png)

#### 6.2.3 Why RCFile behaves this way

**How RCFile stores data.** RCFile (Record Columnar File, He et al., ICDE 2011) first splits the table horizontally into *row groups* (4 MB by default). Inside each row group it stores the data *column by column*: all `station_id` values, then all `country_code` values, and so on. A metadata header records each column chunk's length. Two properties follow:
- a whole row is always inside one HDFS block, so MapReduce can split the file without reassembling rows across machines;
- a reader can **skip the column chunks it does not need**.

**Where it helped and why:**
1. **Column pruning** is the main effect. Q4 needs only `year` and `value`, and Q1 only `element` and `value`. Hive's `LazyBinaryColumnarSerDe` passes the projected column list to `RCFileRecordReader`, which reads only those chunks. **HDFS bytes read fell by 70–72 %** (3,368 MB → 938–1,020 MB). Q3 and Q5 need 4 columns, including the wide `station_id`, and saved 57 % and 38 %.
2. **Lazy decoding.** Columns that are read but filtered out early (e.g. `value` for rows whose `element` is not TMAX) are only decoded when needed.
3. **Smaller files** (−14 %), even without compression. The text format stores a tab and newline per field and row, and writes numbers as characters. RCFile (with `LazyBinaryColumnarSerDe`) stores field lengths in the row-group header and writes numbers in binary.

**Where it did *not* help, and why:**
1. **Q2 (`SELECT *`) gained nothing (1.01×).** It needs all 10 columns, so nothing can be pruned. RCFile even used **47 % more CPU** (227 s vs 154 s) because every row has to be reassembled from 10 separate column buffers. Columnar formats are designed for analytic projections, not for "give me the whole record" access.
2. **Wall-clock gains (1.3×) are much smaller than I/O savings (−70 %).** Three reasons:
   - (a) Every query pays a **fixed MapReduce overhead**: Hive compilation, job submission, ApplicationMaster start-up, about 1 s of JVM start-up per container, and a second stage for ORDER BY/joins. That is roughly 20–35 s per job, regardless of data size.
   - (b) On a laptop SSD, with the data partly in the OS page cache, **disk I/O was not the bottleneck**. Total task CPU for Q1 was almost identical (196 s TEXT vs 191 s RC), so the jobs are CPU-bound on deserialisation and aggregation.
   - (c) Both formats ran with a similar number of map tasks (14 vs 12), because Hive's `CombineHiveInputFormat` packs splits into ~256 MB chunks. The parallelism therefore did not change.
3. **Uncompressed RCFile is only 14 % smaller.** Numbers are binary, but the string columns are stored as raw bytes. The widest column, the 11-character `station_id`, dominates the size and does not shrink at all. The real storage win comes from **compression**. Similar values sit next to each other in a column (e.g. thousands of identical `country_code` or `element` values), so Snappy compressed RCFile 5.5× further (to 551 MB) and cut query times to 40–79 s. This happened even though Snappy is a fast, light codec.
4. **ORC is the modern successor.** It adds lightweight type-specific encodings (run-length, dictionary), stripe-level min/max statistics and ZLIB. It was 14× smaller than text and 3.5× faster in total. With very few files it also needed just 1–2 map tasks, which removed most of the per-task overhead. This is why ORC/Parquet have replaced RCFile in practice, but RCFile introduced the row-group + columnar idea they build on.

**Measurement caveats.** TEXTFILE runs varied more (Q5: 118–177 s) than RCFile runs. This is consistent with reading 3.4 GB through the shared page cache on a laptop that also hosted the other containers. Averaging three runs smooths but does not remove that noise. All runs used the same cluster, the same YARN settings, and `hive.fetch.task.conversion=none`, so every query really ran as MapReduce.

