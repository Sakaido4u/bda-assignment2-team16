## 5. Analysis, Results, and Discussion

This section reports the Part 1 results theme by theme. The Part 2 dashboard is covered in Section 4, and all timing comparisons are collected in Section 6.

### 5.1 Theme 1 – MongoDB Big Data Processing and Analytics

#### 5.1.1 Document design

The by_year file has one row per station, per day, per element. We store **one document per station-day** and **embed** that day's readings as an array:

```javascript
{ station_id: "IN009010100", country_code: "IN",
  date: ISODate("2023-03-17"), year: 2023, month: 3, day: 17,
  readings: [ { element: "TMAX", value: 33.0, m_flag: "", s_flag: "S" },
              { element: "TMIN", value: 20.0, m_flag: "", s_flag: "S" },
              { element: "PRCP", value: 3.0,  m_flag: "", s_flag: "S" } ] }
```

Why we chose this design:

1. A day's readings are almost always read together. Embedding them gives one document read instead of up to five.
2. 57.1 M readings collapse into **20.4 M documents (2.8× fewer)**, which makes the `{station_id, date}` index 2.8× smaller as well.
3. The array is **bounded** (at most 5 elements), so documents never grow without limit. This is the main condition for embedding instead of referencing.
4. The array gives `$unwind`, `$elemMatch` and a **multikey** index something real to work on.
5. Station metadata (name, coordinates) changes rarely and is shared by ~1,000 days, so it is **referenced** through `station_id` and joined with `$lookup` only when needed. Copying it into every day would add ~100 bytes × 20 M documents.

Year, month and day are stored as separate fields next to `date`, so grouping needs no date operators. `country_code` is pre-computed for the same reason.

#### 5.1.2 Ingestion

`mongodb/ingest.py` streams each gzip file once with the same cleaning rules as Pig (core elements, empty Q_FLAG, no −9999) and converts tenths to °C/mm. The files are sorted by date, so the script buffers one date, groups that date's rows by station, and calls `insert_many(batch, ordered=False)` every 10,000 documents. A `tqdm` progress bar shows bytes processed (Fig. A50).

To keep the working set inside the laptop's 0.5 GB WiredTiger cache, we excluded the **US1\* CoCoRaHS** network: volunteer rain gauges that report only precipitation and make up 46 % of all station-days. This is configurable via `MONGO_EXCLUDE_PREFIX` in `.env`; an empty value loads everything.

| Metric | Value |
|---|---|
| Input rows scanned | 113,135,524 (2023–2025) |
| Readings kept | 57,066,860 (QC-failed removed: 84,027, the same count as Pig; other elements: 26,179,943; US1 excluded: 29,804,694) |
| **Documents inserted** | **20,386,429** in `ghcn.observations` (+ 133,039 in `ghcn.stations`, 219 in `ghcn.countries`) |
| Time / throughput | 591.7 s → **34,454 documents/s** |
| Size | 6,233 MB of BSON (320 B/document) → **852 MB on disk** (WiredTiger snappy, 7.3×) |

**Alternative – `mongoimport`.** `mongodb/mongoimport_demo.ps1` pipes `data/stations.jsonl` into `mongoimport --numInsertionWorkers 4`. It imported 133,039 documents with GeoJSON locations in 8.6 s (Fig. A52). mongoimport is ideal when the file already has the target shape. The observations, however, need grouping (several CSV rows → one document), which mongoimport cannot do. That is why we used a pymongo script.

#### 5.1.3 Indexes

| Collection | Index | Type | Size | Build time | Serves |
|---|---|---|---|---|---|
| observations | `{_id: 1}` | default | 214.8 MB | – | – |
| observations | `{station_id: 1, date: 1}` | compound | 304.4 MB | 36.9 s | one station / date range, anchored `^IN` prefix, `$lookup` by station |
| observations | `{"readings.element": 1}` | **multikey** (one key per array element) | 263.2 MB | 77.6 s | `$elemMatch` on element |
| stations | `{location: "2dsphere"}` | geospatial | 2.2 MB | 0.6 s | `$geoNear`, `$geoWithin` |

`db.collection.getIndexes()` output is shown in Fig. A53.

#### 5.1.4 Aggregation pipelines (`mongodb/queries.js`)

| # | Question | Stages | Key result |
|---|---|---|---|
| Q1 | Yearly average TMAX/TMIN per country | `$unwind $match $group $group $lookup $project $sort $limit` | USA 2023: 17.38 / 5.03 °C from 5.30 M readings; India 2023–25: 32.2 / 20.7, 32.3 / 21.2, 31.6 / 22.2 °C |
| Q2 | Top-10 hottest and wettest stations in India | `$match(^IN) $unwind $facet{ $match $group $sort $limit $lookup $project }` | hottest **Madurai 36.5 °C**, Tiruchchirappalli 36.1, Barmer 35.1; wettest **Mahabaleshwar 12,770 mm**, Mangalore 11,373, Goa 9,821 (3-year totals) |
| Q3 | Monthly precipitation totals for one station (Bangalore, IN009010100) | `$match $unwind $match $group $project $sort` | 19 station-months; GHCN receives only ~150 Indian PRCP days/year for this station (reported_days column) |
| Q4 | Extreme-heat days (TMAX > 40 °C) per year | `$match($elemMatch) $unwind $match $group($addToSet) $project($size) $sort` | 2023: 36,286 station-days at 2,416 stations; 2024: 35,509 (max **53.9 °C**); 2025: 24,437 |
| Q5 | One-call summary | `$facet{ temperature, precipitation, stations_per_country, tmax_histogram($bucket) }` | TMAX avg 17.11 °C (13.10 M readings, range −79…53.9); PRCP avg 2.42 mm, max 861.2 mm, 4.21 M wet days; most stations: US 9,519, AU 4,230, CA 2,148 |
| Q6 | Stations within 200 km of Bengaluru | `$geoNear $project $limit` | 309 stations; nearest BANGALORE 1.4 km |
| Q7 | Climate of those stations | `$geoNear $lookup(pipeline: $unwind $group) $match $project($map)` | Bangalore avg TMAX 29.7 °C, TMIN 20.5 °C; Salem 34.8 / 22.5 °C |

The TMAX histogram from Q5's `$bucket` (13.1 M readings):

| °C | <−20 | −20…−10 | −10…0 | 0…10 | 10…20 | 20…30 | 30…40 | 40…50 | ≥50 |
|---|---|---|---|---|---|---|---|---|---|
| readings | 78,772 | 215,307 | 893,491 | 2,503,974 | 3,336,451 | 3,915,428 | 2,045,617 | 110,310 | 176 |

**Interpretation.**
- The hottest Indian stations by average daily maximum are in interior Tamil Nadu (Madurai, Tiruchchirappalli) and the Thar desert (Barmer, Jaisalmer).
- The wettest are all on the Western Ghats/Konkan coast (Mahabaleshwar, Mangalore, Goa, Ratnagiri, Honavar), which matches the south-west monsoon pattern.
- Extreme heat was most widespread in 2023–2024. The lower 2025 count partly reflects fewer reporting stations (1,492 vs 2,416).
- The dashboard's country charts (Fig. B2) show India's pre-monsoon peak (avg TMAX ≈ 38 °C in May 2024) and the July–September rainfall maximum.

#### 5.1.5 Query profiling before and after indexing

`mongodb/profile_queries.py` first drops every secondary index. It then runs each query with `explain("executionStats")` and times 3 real executions, creates the indexes, and repeats the measurements (`results/mongo_profile.csv`, Fig. A60):

| Query | Plan before | Plan after | Docs examined before → after | Keys examined after | Avg time before → after | Speed-up |
|---|---|---|---|---|---|---|
| P1 monthly PRCP, one station | COLLSCAN | IXSCAN | 20,386,429 → 1,053 | 1,053 | 10,028 → **6.0 ms** | ~1,670× |
| P2 one station, Jan–Mar 2025 (`find`) | COLLSCAN | IXSCAN | 20,386,429 → 87 | 87 | 9,604 → **3.8 ms** | ~2,500× |
| P3 hottest Indian stations (`^IN`) | COLLSCAN | IXSCAN | 20,386,429 → 128,561 | 128,562 | 12,999 → **2,136 ms** | 6.1× |
| P4 extreme-heat days (`$elemMatch`) | COLLSCAN | IXSCAN (multikey) | 20,386,429 → 13,099,595 | 13,099,595 | 17,061 → **30,267 ms** | **0.56× (slower)** |
| P5 stations within 200 km (`$geoWithin`) | COLLSCAN | IXSCAN (2dsphere) | 133,039 → 407 | 433 | 135.6 → **3.2 ms** | 42× |
| P6 yearly country averages (full aggregation) | COLLSCAN | COLLSCAN | 20,386,429 → 20,386,429 | 0 | 58,020 → 60,552 ms | 1.0× |

![Fig. R4: MongoDB query time before/after indexing](../results/charts/mongo_profile_time.png)
![Fig. R5: documents examined before/after indexing](../results/charts/mongo_profile_docs.png)

**Discussion.**
- **Selective predicates benefit enormously.** P1, P2 and P5 touch 0.0005–0.3 % of the documents. The B-tree (or the S2 cells of the 2dsphere index) jumps straight to them, so the number of documents examined equals the number returned (*docs examined = keys examined = nReturned*), which is the ideal plan shape.
- **P3** shows that an anchored regex (`^IN`) is a range scan on the compound index's prefix. It still needs 128 k documents and the `$group`, so the gain is 6×, not 1,000×.
- **P4 got slower with the index.** `readings.element = "TMAX"` matches 64 % of all documents. Following 13.1 M index entries means 13.1 M random document fetches, which is worse than one sequential scan. The planner chose the index because it was the only candidate. MongoDB's planner does not cost a COLLSCAN against an available index for `$elemMatch`. *A low-selectivity index should not be created, or the query should be hinted with `{$natural: 1}`.* It would only help with a compound `{readings.element, readings.value}` index on a selective condition (e.g. value > 40, ≈ 0.8 % of TMAX readings).
- **P6 is a control query.** It aggregates everything, so no index can help; the time is dominated by `$unwind` + `$group` over 57 M readings.
- Index cost: 568 MB for the two secondary indexes on a collection that takes 852 MB on disk, plus 115 s to build. Indexes are a trade-off of write speed and space against read speed.
