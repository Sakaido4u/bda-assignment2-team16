#### 5.3.2 Hive tables

`hive/01_create_tables.hql` (run through beeline on HiveServer2; Fig. A43–A45):

| Table | Storage | How it was created | Rows | Size (one replica) | Files |
|---|---|---|---|---|---|
| `obs_text` | TEXTFILE, tab-delimited, **external** over `/ghcn/clean` | `CREATE EXTERNAL TABLE … LOCATION '/ghcn/clean'` (no data copied) | 86,871,554 | 3,531.4 MB | 123 |
| `obs_rc` | **RCFile**, uncompressed, same 10 columns | `CREATE TABLE … STORED AS RCFILE; INSERT OVERWRITE TABLE obs_rc SELECT * FROM obs_text` (262.6 s) | 86,871,554 | 3,034.3 MB | 14 |
| `stations`, `countries` | TEXTFILE, external | over `/ghcn/stations`, `/ghcn/countries` | 133,039 / 219 | 9.2 MB | 1 |
| *Bonus* `obs_rc_snappy` | RCFile + **Snappy** block compression | `CREATE TABLE … LIKE obs_rc` + `SET hive.exec.compress.output=true` (101.4 s) | 86,871,554 | 551.4 MB | 14 |
| *Bonus* `obs_orc` | **ORC** + ZLIB (reference point) | `STORED AS ORC TBLPROPERTIES ('orc.compress'='ZLIB')` (164.8 s) | 86,871,554 | 247.2 MB | 14 |
| *Bonus* `monthly_summary` | RCFile | CTAS: country × year × month × element aggregates joined with `countries` | 19,727 | 0.96 MB | 12 |

Both `COUNT(*)`s return 86,871,554, the exact Pig output count, so no row was lost or duplicated during conversion. `DESCRIBE FORMATTED obs_rc` confirms `InputFormat: org.apache.hadoop.hive.ql.io.RCFileInputFormat` and `SerDe: …columnar.LazyBinaryColumnarSerDe` (Fig. A45).

#### 5.3.3 Benchmark query set (`hive/benchmark_queries.hql`)

The same five HQL statements were run against every table. Only the table name changes (`${TBL}`):

| # | Purpose | Query (abridged) | Columns read (of 10) | Result |
|---|---|---|---|---|
| Q1 | full scan with aggregation | `SELECT element, COUNT(*), AVG(value), MIN(value), MAX(value) … GROUP BY element` | 2 | 5 rows, e.g. TMAX: 13,099,595 readings, avg 17.11 °C, −79.0…53.9 |
| Q2 | filter on one column, return **all** columns | `SELECT * … WHERE country_code='IN' AND element='TMAX' AND value >= 45` | 10 | 469 Indian readings ≥ 45 °C (Barmer, Jaisalmer, Chandrapur …) |
| Q3 | GROUP BY country and year | `SELECT country_code, year, AVG(value), COUNT(*) … WHERE element='TMAX' GROUP BY country_code, year` | 4 | 555 rows |
| Q4 | **only 2 of 10 columns** | `SELECT year, SUM(value), MAX(value) … GROUP BY year` | 2 | 3 rows |
| Q5 | join with stations | `… o JOIN stations s ON o.station_id = s.station_id WHERE o.country_code='IN' AND o.element='TMAX' GROUP BY s.name … ORDER BY avg_tmax DESC LIMIT 10` | 4 (+ stations) | **Madurai 36.52 °C**, Tiruchchirappalli 36.07, Barmer 35.11 … |

**Cross-check between engines.** Hive Q1 over the Pig output gives *exactly* the same TMAX/TMIN counts, averages and extremes as MongoDB Q5 (13,099,595 TMAX readings, avg 17.11 °C, max 53.9 °C). Hive Q5 returns the same top-10 hottest Indian stations, with the same averages and day counts, as MongoDB Q2. The MongoDB load excluded only US1\* stations, which report precipitation only, so temperature results agree to the last digit. This independently validates both cleaning pipelines (Pig and `ingest.py`).

`hive/benchmark_hive.sh` runs each query through beeline and records the time HiveServer2 reports (`N rows selected (X seconds)`). After all runs, `collect_counters.py` matches every run with the MapReduce jobs started inside its time window via the JobHistory REST API and sums their `HDFS_BYTES_READ`, task counts and CPU time. TEXTFILE and RCFile were run **3 times** each (30 runs); the bonus tables once each (10 runs). Results are in Section 6.2.
