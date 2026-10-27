-- Benchmark query set. ${TBL} is replaced by benchmark_hive.sh with obs_text / obs_rc / ...
-- Each query is separated by a line "-- @Qn <description>".

-- @Q1 Full scan with aggregation (statistics per element over every row)
SELECT element, COUNT(*) AS n, ROUND(AVG(value),2) AS avg_v, MIN(value) AS min_v, MAX(value) AS max_v
FROM ${TBL} GROUP BY element;

-- @Q2 Filter on one column (all columns of rows with country_code = 'IN' and TMAX >= 45 C)
SELECT * FROM ${TBL} WHERE country_code = 'IN' AND element = 'TMAX' AND value >= 45.0;

-- @Q3 GROUP BY country and year (average TMAX)
SELECT country_code, year, ROUND(AVG(value),2) AS avg_tmax, COUNT(*) AS n
FROM ${TBL} WHERE element = 'TMAX' GROUP BY country_code, year;

-- @Q4 Only 2 of 10 columns (columnar advantage: year and value)
SELECT year, ROUND(SUM(value),1) AS total, MAX(value) AS max_v FROM ${TBL} GROUP BY year;

-- @Q5 Join with stations (10 hottest Indian stations by average TMAX)
SELECT s.name, s.latitude, s.longitude, ROUND(AVG(o.value),2) AS avg_tmax, COUNT(*) AS n
FROM ${TBL} o JOIN stations s ON (o.station_id = s.station_id)
WHERE o.country_code = 'IN' AND o.element = 'TMAX'
GROUP BY s.name, s.latitude, s.longitude HAVING COUNT(*) > 300
ORDER BY avg_tmax DESC LIMIT 10;
