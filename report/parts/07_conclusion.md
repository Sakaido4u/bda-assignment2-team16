## 7. Conclusion

### 7.1 Summary of what was achieved

**Part 1.**
- We built a working **three-node Hadoop 3.3.6 cluster** (one master, two workers) from a single custom Docker image, plus PostgreSQL, MongoDB and a Flask container. All configuration is generated from one `.env` file, so the same project can be redeployed on three real machines through a Swarm overlay network or a native install script.
- **Distribution was proven at every level.** All 126 HDFS blocks of the raw data have one replica on each worker (`fsck`, NameNode file browser). Every MapReduce, Pig and Hive job ran its tasks on both NodeManagers (JobHistory per-attempt node column, REST-API task counts).
- **Theme 2.** 113 million GHCN-Daily records (3.8 GB, 2023–2025) were processed with:
  - Java MapReduce, using a custom Writable, a Combiner that cut the shuffle 1,262× and custom data-quality counters;
  - Python Streaming, which produced identical results and was 39 % slower.
- **Theme 3.** Pig cleaned the data in MapReduce mode (86,871,554 valid records; 84,027 QC failures removed) in one multi-query pass. In Hive, **RCFile read 50 % less data from HDFS and ran the benchmark 1.26× faster than TEXTFILE overall**. For queries touching 2 of 10 columns the read reduction was 70–72 %, and there was **no gain for `SELECT *`**. Uncompressed RCFile was only 14 % smaller. With Snappy it was 6.4× smaller, and ORC reached 14.3×.
- **Theme 1.** MongoDB held 20.4 M station-day documents with embedded readings. Seven aggregation pipelines covered `$match/$group/$project/$unwind/$facet/$lookup/$bucket/$geoNear`. Indexing turned selective queries from ~10 s COLLSCANs into **4–6 ms IXSCANs (≈ 2,000×)**. It also showed that a low-selectivity multikey index makes a query **slower** (17 s → 30 s).
- **Validation across engines.** Hive (over Pig's output) and MongoDB (over `ingest.py`'s output) produced identical temperature statistics and identical top-10 station rankings.

**Part 2.** The Flask dashboard makes all of this visible:
- live node cards and HDFS/YARN metrics from the Hadoop REST APIs;
- climate charts from MongoDB aggregation results;
- a Leaflet station map backed by the 2dsphere index;
- safe, parameterised Hive queries that run on the cluster;
- charts of every Part 1 measurement;
- clear error messages when a service is down.

**Main findings about the tools.**
- *MapReduce* is reliable but verbose.
- *Pig* is ideal for multi-step cleaning, and its multi-query optimiser saves full passes.
- *Hive* makes SQL analysis easy, but its MapReduce engine adds a 20–35 s fixed cost per query.
- *Columnar storage* pays off through column pruning and compression, not by itself.
- *MongoDB* is best for selective, indexed and geospatial access to semi-structured documents, not for full-collection analytics.

### 7.2 Limitations

1. **One physical machine.** The three "nodes" share 8 logical CPUs, one SSD and 7.66 GiB of RAM. That gives real distribution semantics (separate hosts, network transfer, replication, scheduling) but not real parallel hardware, so absolute times are pessimistic. Mode B was prepared and its configuration validated, but not run on three physical computers.
2. **Data subset.** We used three years (2023–2025), not the full 1750–present archive. For MongoDB we excluded the US1\* CoCoRaHS precipitation-only network to fit the laptop's memory.
3. **Hive on MapReduce.** Hive 3 supports Tez and LLAP, which would remove most of the per-query start-up overhead; we kept MapReduce as the course requires.
4. **Benchmark noise.** Three runs per query on a shared laptop leave ±15 % variance on TEXTFILE runs. The bonus formats were run once only.
5. **Data quality.** We filter on Q_FLAG only. Station coverage is uneven: India contributes ~155 stations, and GHCN receives only some Indian precipitation days.

### 7.3 Future work

- Run Mode B on three lab machines and compare scaling (1 vs 2 vs 3 workers), varying the block size, split size and reducer counts (the Option 2 extension).
- Switch Hive to the **Tez** engine and add **ORC/Parquet** with partitioning by `year` and bucketing by `station_id`, so queries can skip partitions entirely.
- Run a **MongoDB replica set** across the three nodes for fault tolerance, and test sharding on `station_id`.
- Add incremental daily ingestion: NOAA updates the current-year file every day. A Kafka → HDFS/MongoDB pipeline would add the *velocity* dimension.
- Compute climate indicators (heat-wave spells, monsoon onset, decadal trends) over the full 1901–2025 record with Spark.

