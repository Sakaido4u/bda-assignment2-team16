## 4. Implementation of the Selected Practical Extension (Part 2)

**Selected option: Option 3 – Web Dashboard and Visualization (Python Flask).**

The Part 1 summary is in Section 5. This section describes only the Part 2 extension.

### 4.1 Goal and design

The dashboard turns the cluster and the analytics of Part 1 into something an examiner can *see*: the three nodes working together, the climate results, the stations on a map, Hive running on the cluster, and the measured performance differences. It runs as its own container (`dashboard`, image `bda16/dashboard:1.0`) on the same Docker network. It talks to the other services by hostname and never through the Windows host.

| Layer | Choice | Reason |
|---|---|---|
| Web framework | Flask 3.0 behind Gunicorn (2 workers × 4 threads, 600 s timeout) | small, Pythonic; the long timeout lets a Hive query run as a full MapReduce job |
| Data access | `requests` (NameNode JMX, ResourceManager REST), `pymongo` 4.8, `PyHive` 0.7 (Thrift/SASL to HiveServer2) | official, stable client libraries |
| UI | Bootstrap 5.3 (responsive grid), Chart.js 4.4, Leaflet 1.9 + OpenStreetMap tiles | vendored locally, so the pages load without internet (except map tiles) |
| Configuration | same `.env` (`MASTER_HOST`, `MONGO_HOST`, …) | works unchanged in Mode B |

```
dashboard/
├── app.py                # routes + JSON APIs
├── Dockerfile, requirements.txt
├── templates/            # base.html + overview, climate, map, hive, performance
└── static/  css/app.css, js/common.js, vendor/ (bootstrap, chart.js, leaflet)
```

Every page is rendered server-side as a template and then fills itself from small JSON endpoints (`/api/...`). Each endpoint wraps the external call. If a service is unreachable, the API returns HTTP 503 with a readable message (e.g. *"MongoDB unavailable: ServerSelectionTimeoutError"*, *"NameNode is starting up"*), and the page shows it as a red Bootstrap alert instead of failing silently. We tested this while the master container was restarting and before MongoDB was loaded (Fig. B7).

### 4.2 Page 1 – Cluster Overview (`/`)

- `GET /api/cluster` combines three live sources:
  - **NameNode JMX:** `/jmx?qry=Hadoop:service=NameNode,name=NameNodeInfo` (per-DataNode `LiveNodes` JSON: used/remaining bytes, block count, last contact) and `…name=FSNamesystemState` (live/dead DataNodes, capacity, files, blocks, under-replicated blocks).
  - **ResourceManager REST:** `/ws/v1/cluster/info`, `/metrics`, `/nodes`, `/apps`.
  - **MongoDB** `ping` and collection counts.
- The page refreshes every 10 s. It shows four KPI tiles (live DataNodes, active NodeManagers, HDFS used, YARN memory in use) and **one card per node** (master, worker1, worker2) with its daemons, a RUNNING/DOWN badge, and the DataNode and NodeManager details. It also shows a bar chart of HDFS storage per DataNode and the 12 most recent YARN applications with live progress.
- After a NodeManager restart, YARN keeps the old SHUTDOWN entry for the same host. The API prefers the RUNNING entry so the card does not show a false "DOWN".
- Fig. B1 was captured while the Pig cleaning job was running. Both workers show 3 containers and 1,536/1,536 MB in use, which is direct visual proof that the work is spread over the two workers.

### 4.3 Page 2 – Climate Analytics (`/climate`)

Aggregating ~19 million station-day documents on every page view would take tens of seconds. `mongodb/build_summaries.py` therefore runs **one MongoDB aggregation pipeline** (`$unwind → $group by country/year/month/element → $lookup countries → $project → $merge`) that materialises `ghcn.summary_country_month`. The collection holds averages, sums, min/max, counts, station counts and the number of readings above 40 °C. The page reads this small collection (indexed by country/year/month) and draws:

1. average TMAX/TMIN per year for the selected country (the tooltip shows heat days);
2. average daily precipitation per month, one line per year;
3. monthly average TMAX, one line per year;
4. the top 15 countries by extreme-heat station-days (TMAX > 40 °C).

The country selector lists every country with at least 1,000 TMAX readings. The country code is validated with a regex (`^[A-Z]{2}$`) before it reaches MongoDB.

### 4.4 Page 3 – Station Map (`/map`)

- `GET /api/stations/near?lat=&lon=&km=` runs a `$geoNear` aggregation on `ghcn.stations`. It **requires the 2dsphere index** on `location` and returns up to 500 stations with their distance. Coordinates are range-checked, and the radius is capped at 1,000 km.
- The page starts at Bengaluru (12.97 N, 77.59 E) with a 200 km radius. The user can type coordinates, click anywhere on the map, or press **"Stations near me"** (browser geolocation).
- Clicking a station calls `GET /api/station/<id>`. That runs an indexed aggregation over `ghcn.observations` (`$match station_id` → `$unwind readings` → `$group by element`) and shows avg/min/max/count and the reporting period of every element. The page also shows the query time in milliseconds.

### 4.5 Page 4 – Hive Queries (`/hive`)

- Four **predefined** HQL queries are defined in `HIVE_QUERIES` in `app.py`:
  1. monthly averages for a country, element and year (`monthly_summary`);
  2. top N countries by yearly average;
  3. observation counts per element and year;
  4. hottest stations of a country in a year: a full scan of the 80-million-row RCFile table `obs_rc` **joined** with `stations`.
- **No free-text SQL is accepted.** The parameters come from drop-downs, and the server validates them again against white-lists:
  - country `^[A-Z]{2}$`;
  - element ∈ {TMAX, TMIN, PRCP, SNOW, SNWD};
  - year ∈ {2023, 2024, 2025};
  - limit an integer clamped to 1–50.

  The values are then passed to PyHive as bound parameters (`cursor.execute(sql, params)`), which escapes them. SQL injection is therefore impossible by construction.
- The page shows the exact HQL that ran, the result table and the execution time measured around the HiveServer2 call. Each query runs as one or more MapReduce jobs on YARN, which can be watched on the Cluster page or in the RM UI at the same time.

### 4.6 Page 5 – Performance (`/performance`)

`GET /api/performance` reads the CSV files produced in Part 1 (`results/` is mounted read-only into the container) and draws:

- MongoDB query time and documents examined, **before vs after indexing**, on a log scale, plus the full `explain()` table with COLLSCAN/IXSCAN badges;
- Hive average query time and HDFS MB read per query for **TEXTFILE vs RCFile** (plus the bonus Snappy-RCFile and ORC tables);
- Hive storage size per format;
- MapReduce wall time for Java vs Python Streaming.

### 4.7 UI, accessibility and robustness

- Responsive Bootstrap grid: KPI tiles go from 4 → 2 → 1 per row, and charts stack on narrow screens.
- One fixed, colour-blind-checked categorical palette (blue, orange, aqua, …), assigned in a fixed order. Text always uses neutral ink colours. There are no dual-axis charts; a second measure goes into the tooltip or a separate chart.
- All dynamic text is HTML-escaped in the browser (`escapeHtml`). API inputs are validated server-side.
- Health endpoint `/health`. The container restarts automatically (`restart: unless-stopped`).

### 4.8 How to run

```powershell
docker compose run --rm tools python mongodb/build_summaries.py   # once, after ingestion
docker compose up -d --no-deps dashboard                         # (already started by start-cluster.ps1)
start http://localhost:5000
```

Screenshots of every page are in Appendix B (Fig. B1–B8).
