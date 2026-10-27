### 5.3 Theme 3 – Pig Latin and Hive RCFile Performance

#### 5.3.1 Pig cleaning (MapReduce mode)

`pig/clean_ghcn.pig` runs with `pig -x mapreduce`, so every statement is compiled to MapReduce jobs on YARN. Local mode is not used. The steps:

1. `LOAD '/ghcn/raw' USING PigStorage(',') AS (station_id:chararray, obs_date:chararray, element:chararray, data_value:int, m_flag, q_flag, s_flag, obs_time)`: an explicit schema.
2. `FILTER` to the five core elements, then keep only rows whose `q_flag` is null or empty (failed-QC rows are removed). Also drop `-9999`/null values and malformed ids/dates.
3. `FOREACH … GENERATE`:
   - convert units: TMAX/TMIN/PRCP ÷ 10 → °C / mm, while SNOW/SNWD are already mm;
   - split `obs_date` into `year`, `month`, `day` with `SUBSTRING` + casts;
   - derive `country_code = SUBSTRING(station_id, 0, 2)`;
   - replace null flags with empty strings.
4. `STORE` tab-separated into `/ghcn/clean`. In the same script, five `GROUP … ALL / COUNT_STAR` branches count the records at each stage. Pig's **multi-query optimiser** merged all of this into one 122-map job that reads the input once, and the counts are stored in `/ghcn/clean_stats`.

The joins with stations and countries are done later in Hive (`stations`, `countries` tables). Copying station names into all 87 M rows would have doubled the size of the cleaned data.

`pig/inspect_sample.pig` demonstrates the operators on a 5,000-row sample that includes Indian stations and QC-failed rows (Fig. A38–A39):

- `DESCRIBE raw` / `DESCRIBE clean` print the schemas before and after transformation.
- `DUMP qc_show` lists rows with Q_FLAG `I` (internal consistency failure), which are removed.
- `DUMP india_show` shows cleaned Indian TMAX/TMIN rows, e.g. `(IN019040100,IN,2025,1,1,TMAX,25.6)`.
- The per-element before/after comparison on the sample: PRCP 2004 → 1946, TMAX 918 → 772, TMIN 1063 → 929, SNWD 35 → 3.
- `ILLUSTRATE clean` follows sample rows through `raw → core → valid → clean`. The rows Pig picked all carried Q_FLAG `I`, so they appear in `raw` and `core` and disappear at `valid`. ILLUSTRATE thus shows the QC filter at work.

**Full run** (job `job_…_0007`, 122 maps + 1 reduce, then a 5-map job for the counts; Fig. A40–A41):

| Stage | Records | Change |
|---|---|---|
| 1. Raw records read | 113,135,524 | 4.07 GB |
| 2. Core elements (TMAX, TMIN, PRCP, SNOW, SNWD) | 86,955,581 | −26,179,943 other elements |
| 3. Removed: failed quality control (non-empty Q_FLAG) | 84,027 | 0.097 % of core rows |
| 4. Removed: missing value (−9999) | 0 | the by_year files simply omit missing days (`grep -c ",-9999,"` on 2025.csv = 0); the filter is kept for other GHCN products (.dly files) |
| **5. Clean records stored in `/ghcn/clean`** | **86,871,554** | 3.53 GB (3.3 GiB) in 122 files, 6.6 GiB with replicas |
| Elapsed | 930 s (15.5 min) | average map task 33 s; one reducer for the five counts |

![Fig. R3: Pig cleaning funnel](../results/charts/pig_clean_funnel.png)

Note: MapReduce Job 1 counted 43,210 QC failures and Job 2 counted 25,187, which covers only TMAX/TMIN and PRCP respectively. Pig's 84,027 covers all five core elements. The dataset profile's 125,479 covers every element.
