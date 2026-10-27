#!/usr/bin/env python3
"""Convert the fixed-width GHCN-Daily station and country files into clean CSV/TSV/JSON.

Outputs (in data/):
  stations.csv    quoted CSV with a header (human readable)
  stations.tsv    tab separated, no header   -> HDFS /ghcn/stations (Hive, Pig, MapReduce)
  stations.jsonl  one JSON document per line with a GeoJSON Point -> MongoDB ghcn.stations
  countries.tsv   code<TAB>name, no header   -> HDFS /ghcn/countries

Fixed-width layout of ghcnd-stations.txt (1-based columns, from the GHCN-Daily readme):
  ID 1-11 | LATITUDE 13-20 | LONGITUDE 22-30 | ELEVATION 32-37 | STATE 39-40 |
  NAME 42-71 | GSN FLAG 73-75 | HCN/CRN FLAG 77-79 | WMO ID 81-85
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data")


def field(line, start, end):
    """Return the 1-based inclusive column slice, stripped."""
    return line[start - 1:end].strip()


def load_countries():
    countries = {}
    with open(os.path.join(RAW, "ghcnd-countries.txt"), encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(line) >= 4:
                countries[line[0:2]] = line[3:].strip()
    return countries


def main():
    countries = load_countries()
    stations = []
    with open(os.path.join(RAW, "ghcnd-stations.txt"), encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(line) < 71:
                continue
            sid = field(line, 1, 11)
            elev = float(field(line, 32, 37))
            stations.append({
                "station_id": sid,
                "latitude": float(field(line, 13, 20)),
                "longitude": float(field(line, 22, 30)),
                "elevation": None if elev == -999.9 else elev,   # -999.9 = missing
                "state": field(line, 39, 40),
                "name": field(line, 42, 71),
                "gsn_flag": field(line, 73, 75),
                "hcn_crn_flag": field(line, 77, 79),
                "wmo_id": field(line, 81, 85),
                "country_code": sid[:2],
                "country_name": countries.get(sid[:2], "Unknown"),
            })

    cols = ["station_id", "latitude", "longitude", "elevation", "state", "name",
            "gsn_flag", "hcn_crn_flag", "wmo_id", "country_code", "country_name"]

    with open(os.path.join(OUT, "stations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(stations)

    with open(os.path.join(OUT, "stations.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for s in stations:
            f.write("\t".join("" if s[c] is None else str(s[c]).replace("\t", " ") for c in cols) + "\n")

    with open(os.path.join(OUT, "stations.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for s in stations:
            doc = dict(s)
            # GeoJSON order is [longitude, latitude]
            doc["location"] = {"type": "Point", "coordinates": [s["longitude"], s["latitude"]]}
            f.write(json.dumps(doc) + "\n")

    with open(os.path.join(OUT, "countries.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for code, name in sorted(countries.items()):
            f.write(f"{code}\t{name}\n")

    n_countries = len({s["country_code"] for s in stations})
    print(f"stations: {len(stations):,}  countries with stations: {n_countries}  country codes: {len(countries)}")
    print(f"written: stations.csv, stations.tsv, stations.jsonl, countries.tsv -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
