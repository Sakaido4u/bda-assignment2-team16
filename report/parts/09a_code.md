## 9. Appendices – Code and Screenshots

### Appendix C – Code listing (all files are in the submitted project folder)

| Area | File | Purpose |
|---|---|---|
| Cluster | `.env` | every tunable value (hosts, IPs, block size, memory, years) |
| | `docker/hadoop/Dockerfile` | single image: Temurin 8 + Hadoop 3.3.6 + Hive 3.1.3 + Pig 0.18.0, Guava fix |
| | `docker/hadoop/entrypoint.sh` | starts master or worker daemons; formats NameNode / inits metastore only once |
| | `docker/hadoop/render-config.sh`, `templates/*.xml.template` | config files rendered from environment variables |
| | `docker-compose.yml` | Mode A (one laptop) |
| | `docker-compose.master.yml`, `docker-compose.worker.yml`, `docker-stack.yml`, `install-native.sh` | Mode B (three machines; Swarm overlay or native) |
| | `scripts/start-cluster.ps1`, `cluster-status.ps1`, `stop-cluster.ps1`, `reset-cluster.ps1`, `fetch-tarballs.ps1` | cluster lifecycle |
| Dataset | `scripts/download-data.ps1` / `.sh`, `prepare_stations.py`, `dataset_stats.py` | download, fixed-width → CSV/TSV/GeoJSON, profiling |
| Theme 1 | `mongodb/ingest.py` | batched `insert_many` of station-day documents |
| | `mongodb/queries.js` | indexes + 7 aggregation pipelines (mongosh) |
| | `mongodb/profile_queries.py` | explain("executionStats") before/after indexing → `results/mongo_profile.csv` |
| | `mongodb/build_summaries.py`, `mongoimport_demo.ps1` | `$merge` summary for the dashboard; mongoimport alternative |
| Theme 2 | `scripts/hdfs-operations.sh` | HDFS commands + fsck replication proof |
| | `mapreduce/src/main/java/edu/jssateb/bda/ghcn/*.java`, `pom.xml`, `build.ps1` | Java jobs (custom Writable, Combiner, counters) |
| | `mapreduce/streaming/mapper.py`, `combiner.py`, `reducer.py` | Python Streaming version of Job 1 |
| | `mapreduce/run-jobs.sh`, `task_nodes.py` | run on YARN, timing, per-node task report |
| Theme 3 | `pig/clean_ghcn.pig`, `inspect_sample.pig`, `run-pig.sh` | cleaning in MapReduce mode |
| | `hive/01_create_tables.hql`, `02_bonus_tables.hql` | TEXTFILE, RCFile (+ Snappy RCFile, ORC, summary) |
| | `hive/benchmark_queries.hql`, `benchmark_hive.sh`, `collect_counters.py`, `run-hive.sh` | 5 queries × 3 runs, HDFS bytes from JobHistory counters |
| Part 2 | `dashboard/app.py`, `templates/*.html`, `static/` , `Dockerfile`, `requirements.txt` | Flask dashboard |
| Report | `scripts/make_charts.py`, `report/tools/capture.py`, `collect_text.sh`, `render_mermaid.py` | charts, screenshots, diagrams |

#### C.1 Key excerpt – custom Writable merged by Combiner and Reducer (`TempStatsWritable.java`)

```java
public class TempStatsWritable implements Writable {
    private long tmaxSum, tmaxCount, tminSum, tminCount;
    public void merge(TempStatsWritable o) {
        tmaxSum += o.tmaxSum;  tmaxCount += o.tmaxCount;
        tminSum += o.tminSum;  tminCount += o.tminCount;
    }
    public double avgTmaxC() { return tmaxCount == 0 ? Double.NaN : tmaxSum / 10.0 / tmaxCount; }
    @Override public void write(DataOutput out) throws IOException {
        out.writeLong(tmaxSum); out.writeLong(tmaxCount); out.writeLong(tminSum); out.writeLong(tminCount);
    }
    @Override public void readFields(DataInput in) throws IOException {
        tmaxSum = in.readLong(); tmaxCount = in.readLong(); tminSum = in.readLong(); tminCount = in.readLong();
    }
}
```

#### C.2 Key excerpt – Pig cleaning (`clean_ghcn.pig`)

```pig
raw   = LOAD '$INPUT' USING PigStorage(',') AS (station_id:chararray, obs_date:chararray,
          element:chararray, data_value:int, m_flag:chararray, q_flag:chararray, s_flag:chararray, obs_time:chararray);
core  = FILTER raw BY element IN ('TMAX', 'TMIN', 'PRCP', 'SNOW', 'SNWD');
qc_ok = FILTER core BY q_flag IS NULL OR TRIM(q_flag) == '';
valid = FILTER qc_ok BY data_value IS NOT NULL AND data_value != -9999 AND SIZE(obs_date) == 8;
clean = FOREACH valid GENERATE station_id, SUBSTRING(station_id, 0, 2) AS country_code,
          (int) SUBSTRING(obs_date, 0, 4) AS year, (int) SUBSTRING(obs_date, 4, 6) AS month,
          (int) SUBSTRING(obs_date, 6, 8) AS day, element,
          ((element == 'SNOW' OR element == 'SNWD') ? (double) data_value : (double) data_value / 10.0) AS value, ...;
STORE clean INTO '$OUTPUT' USING PigStorage('\t');
```

#### C.3 Key excerpt – Hive RCFile table (`01_create_tables.hql`)

```sql
CREATE EXTERNAL TABLE obs_text (station_id STRING, country_code STRING, year INT, month INT, day INT,
  element STRING, value DOUBLE, m_flag STRING, s_flag STRING, obs_time STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE LOCATION '/ghcn/clean';
CREATE TABLE obs_rc (... same columns ...) STORED AS RCFILE;
INSERT OVERWRITE TABLE obs_rc SELECT * FROM obs_text;
```

#### C.4 Key excerpt – MongoDB `$facet` + `$bucket` (`queries.js`, Q5)

```javascript
db.observations.aggregate([{ $facet: {
  temperature:   [{ $unwind: "$readings" }, { $match: { "readings.element": { $in: ["TMAX","TMIN"] } } },
                  { $group: { _id: "$readings.element", avg: { $avg: "$readings.value" }, n: { $sum: 1 } } }],
  precipitation: [{ $unwind: "$readings" }, { $match: { "readings.element": "PRCP" } },
                  { $group: { _id: null, avg_mm: { $avg: "$readings.value" }, max_mm: { $max: "$readings.value" } } }],
  stations_per_country: [{ $group: { _id: "$station_id", c: { $first: "$country_code" } } },
                         { $group: { _id: "$c", stations: { $sum: 1 } } }, { $sort: { stations: -1 } }, { $limit: 10 }],
  tmax_histogram: [{ $unwind: "$readings" }, { $match: { "readings.element": "TMAX" } },
                   { $bucket: { groupBy: "$readings.value", boundaries: [-70,-20,-10,0,10,20,30,40,50,70], default: "out_of_range" } }]
}}], { allowDiskUse: true });
```
