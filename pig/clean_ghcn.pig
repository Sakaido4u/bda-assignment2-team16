/*
 * Theme 3 - Pig Latin cleaning of GHCN-Daily (runs in MapReduce mode on YARN)
 *   pig -x mapreduce -param INPUT=/ghcn/raw -param OUTPUT=/ghcn/clean -f pig/clean_ghcn.pig
 *
 * 1. load raw CSV with an explicit schema
 * 2. keep the five core elements, drop QC-failed (non-empty Q_FLAG) and missing (-9999) values
 * 3. convert units: TMAX/TMIN tenths of deg C -> deg C, PRCP tenths of mm -> mm (SNOW/SNWD already mm)
 * 4. split DATE into year / month / day and derive the country code from the station id
 * 5. store tab-separated output in HDFS for Hive, plus a small record-count report
 */
%default INPUT '/ghcn/raw'
%default OUTPUT '/ghcn/clean'
%default STATS '/ghcn/clean_stats'

SET job.name 'GHCN Pig cleaning (Team 16)';
SET default_parallel 4;

raw = LOAD '$INPUT' USING PigStorage(',') AS (
        station_id:chararray, obs_date:chararray, element:chararray, data_value:int,
        m_flag:chararray, q_flag:chararray, s_flag:chararray, obs_time:chararray);

core     = FILTER raw BY element IN ('TMAX', 'TMIN', 'PRCP', 'SNOW', 'SNWD');
qc_bad   = FILTER core BY q_flag IS NOT NULL AND TRIM(q_flag) != '';
qc_ok    = FILTER core BY q_flag IS NULL OR TRIM(q_flag) == '';
missing  = FILTER qc_ok BY data_value IS NULL OR data_value == -9999;
valid    = FILTER qc_ok BY data_value IS NOT NULL AND data_value != -9999
                         AND SIZE(obs_date) == 8 AND SIZE(station_id) == 11;

clean = FOREACH valid GENERATE
          station_id,
          SUBSTRING(station_id, 0, 2)              AS country_code:chararray,
          (int) SUBSTRING(obs_date, 0, 4)          AS year:int,
          (int) SUBSTRING(obs_date, 4, 6)          AS month:int,
          (int) SUBSTRING(obs_date, 6, 8)          AS day:int,
          element,
          ((element == 'SNOW' OR element == 'SNWD') ? (double) data_value
                                                    : (double) data_value / 10.0) AS value:double,
          (m_flag IS NULL ? '' : m_flag)           AS m_flag:chararray,
          (s_flag IS NULL ? '' : s_flag)           AS s_flag:chararray,
          (obs_time IS NULL ? '' : obs_time)       AS obs_time:chararray;

DESCRIBE raw;
DESCRIBE clean;

rmf $OUTPUT
rmf $STATS
STORE clean INTO '$OUTPUT' USING PigStorage('\t');

-- record counts at each cleaning stage (multi-query: computed in the same pass)
c_raw     = FOREACH (GROUP raw ALL)     GENERATE '1_raw_records'      AS stage, COUNT_STAR(raw)     AS n;
c_core    = FOREACH (GROUP core ALL)    GENERATE '2_core_elements'    AS stage, COUNT_STAR(core)    AS n;
c_qc_bad  = FOREACH (GROUP qc_bad ALL)  GENERATE '3_qc_failed_removed' AS stage, COUNT_STAR(qc_bad) AS n;
c_missing = FOREACH (GROUP missing ALL) GENERATE '4_missing_removed'  AS stage, COUNT_STAR(missing) AS n;
c_clean   = FOREACH (GROUP clean ALL)   GENERATE '5_clean_records'    AS stage, COUNT_STAR(clean)   AS n;
counts = UNION c_raw, c_core, c_qc_bad, c_missing, c_clean;
STORE counts INTO '$STATS' USING PigStorage('\t');
