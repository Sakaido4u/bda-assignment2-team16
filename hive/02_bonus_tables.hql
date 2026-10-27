-- =====================================================================
--  BONUS (extra, beyond the required TEXTFILE vs RCFile comparison)
--    obs_rc_snappy : RCFile with Snappy block compression
--    obs_orc       : ORC (modern columnar format) as a reference point
--    monthly_summary : small aggregate used by the dashboard's Hive page
-- =====================================================================
USE ghcn;

DROP TABLE IF EXISTS obs_rc_snappy;
CREATE TABLE obs_rc_snappy LIKE obs_rc;
SET hive.exec.compress.output=true;
SET mapreduce.output.fileoutputformat.compress.codec=org.apache.hadoop.io.compress.SnappyCodec;
INSERT OVERWRITE TABLE obs_rc_snappy SELECT * FROM obs_text;

DROP TABLE IF EXISTS obs_orc;
CREATE TABLE obs_orc (
  station_id STRING, country_code STRING, year INT, month INT, day INT,
  element STRING, value DOUBLE, m_flag STRING, s_flag STRING, obs_time STRING
)
STORED AS ORC TBLPROPERTIES ('orc.compress'='ZLIB');
SET hive.exec.compress.output=false;
INSERT OVERWRITE TABLE obs_orc SELECT * FROM obs_text;

DROP TABLE IF EXISTS monthly_summary;
CREATE TABLE monthly_summary STORED AS RCFILE AS
SELECT o.country_code, c.name AS country_name, o.year, o.month, o.element,
       ROUND(AVG(o.value), 2) AS avg_value,
       MIN(o.value)           AS min_value,
       MAX(o.value)           AS max_value,
       COUNT(*)               AS n_obs,
       COUNT(DISTINCT o.station_id) AS n_stations
FROM obs_rc o JOIN countries c ON (o.country_code = c.code)
GROUP BY o.country_code, c.name, o.year, o.month, o.element;

SELECT COUNT(*) AS summary_rows FROM monthly_summary;
