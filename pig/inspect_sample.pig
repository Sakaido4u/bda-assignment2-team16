/*
 * Small-sample walkthrough of the cleaning logic for the report/demo:
 * DESCRIBE, ILLUSTRATE and DUMP on a few thousand rows (MapReduce mode).
 *   pig -x mapreduce -param SAMPLE=/ghcn/sample/sample.csv -f pig/inspect_sample.pig
 */
%default SAMPLE '/ghcn/sample/sample.csv'

SET job.name 'GHCN Pig sample inspection (Team 16)';

raw = LOAD '$SAMPLE' USING PigStorage(',') AS (
        station_id:chararray, obs_date:chararray, element:chararray, data_value:int,
        m_flag:chararray, q_flag:chararray, s_flag:chararray, obs_time:chararray);
DESCRIBE raw;

core  = FILTER raw BY element IN ('TMAX', 'TMIN', 'PRCP', 'SNOW', 'SNWD');
valid = FILTER core BY (q_flag IS NULL OR TRIM(q_flag) == '') AND data_value IS NOT NULL AND data_value != -9999;
clean = FOREACH valid GENERATE
          station_id,
          SUBSTRING(station_id, 0, 2)     AS country_code:chararray,
          (int) SUBSTRING(obs_date, 0, 4) AS year:int,
          (int) SUBSTRING(obs_date, 4, 6) AS month:int,
          (int) SUBSTRING(obs_date, 6, 8) AS day:int,
          element,
          ((element == 'SNOW' OR element == 'SNWD') ? (double) data_value : (double) data_value / 10.0) AS value:double;
DESCRIBE clean;

-- rows that failed quality control (non-empty Q_FLAG) - these are removed
qc_failed = FILTER core BY q_flag IS NOT NULL AND TRIM(q_flag) != '';
qc_show   = LIMIT qc_failed 5;
DUMP qc_show;

-- cleaned Indian temperature readings
india = FILTER clean BY country_code == 'IN' AND (element == 'TMAX' OR element == 'TMIN');
india_show = LIMIT india 10;
DUMP india_show;

-- per-element counts in the sample, before vs after cleaning
by_el_raw   = FOREACH (GROUP core BY element)  GENERATE group AS element, COUNT(core)  AS before_cleaning;
by_el_clean = FOREACH (GROUP clean BY element) GENERATE group AS element, COUNT(clean) AS after_cleaning;
cmp = JOIN by_el_raw BY element, by_el_clean BY element;
cmp_out = FOREACH cmp GENERATE by_el_raw::element, before_cleaning, after_cleaning;
DUMP cmp_out;

ILLUSTRATE clean;
