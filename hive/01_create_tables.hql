-- =====================================================================
--  Theme 3 - Hive tables over the Pig-cleaned GHCN data
--  beeline -u jdbc:hive2://master:10000 -n root -f hive/01_create_tables.hql
-- =====================================================================
CREATE DATABASE IF NOT EXISTS ghcn;
USE ghcn;

-- 1) External TEXTFILE table directly over the Pig output (row-oriented, uncompressed)
DROP TABLE IF EXISTS obs_text;
CREATE EXTERNAL TABLE obs_text (
  station_id   STRING,
  country_code STRING,
  year         INT,
  month        INT,
  day          INT,
  element      STRING,
  value        DOUBLE,
  m_flag       STRING,
  s_flag       STRING,
  obs_time     STRING
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/ghcn/clean';

-- 2) Station and country dimension tables
DROP TABLE IF EXISTS stations;
CREATE EXTERNAL TABLE stations (
  station_id   STRING,
  latitude     DOUBLE,
  longitude    DOUBLE,
  elevation    DOUBLE,
  state        STRING,
  name         STRING,
  gsn_flag     STRING,
  hcn_crn_flag STRING,
  wmo_id       STRING,
  country_code STRING,
  country_name STRING
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/ghcn/stations';

DROP TABLE IF EXISTS countries;
CREATE EXTERNAL TABLE countries (code STRING, name STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/ghcn/countries';

-- 3) Identical schema stored as RCFile (row groups, column-wise inside each group)
DROP TABLE IF EXISTS obs_rc;
CREATE TABLE obs_rc (
  station_id   STRING,
  country_code STRING,
  year         INT,
  month        INT,
  day          INT,
  element      STRING,
  value        DOUBLE,
  m_flag       STRING,
  s_flag       STRING,
  obs_time     STRING
)
STORED AS RCFILE;

SET hive.exec.compress.output=false;
INSERT OVERWRITE TABLE obs_rc SELECT * FROM obs_text;

SELECT 'obs_text' AS tbl, COUNT(*) AS row_count FROM obs_text
UNION ALL
SELECT 'obs_rc' AS tbl, COUNT(*) AS row_count FROM obs_rc;
