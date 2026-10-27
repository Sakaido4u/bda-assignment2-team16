#!/usr/bin/env python3
"""Theme 1 - load GHCN-Daily into MongoDB.

  docker compose run --rm tools python mongodb/ingest.py            (years / filters from .env)
  docker compose run --rm tools python mongodb/ingest.py --years 2025 --exclude-prefix ""

Document design - one document per station per day, readings embedded as an array:
  {
    station_id: "IN022021900", country_code: "IN",
    date: ISODate("2025-05-14"), year: 2025, month: 5, day: 14,
    readings: [ {element: "TMAX", value: 41.2, m_flag: "", s_flag: "S"},
                {element: "TMIN", value: 27.0, ...}, {element: "PRCP", value: 0.0, ...} ]
  }
Why: the by_year file has one row per station-day-element (5 rows for a fully equipped station);
grouping them cuts the document count ~2.4x, keeps all readings of a day together (one read per
station-day), and the readings array gives $unwind / $elemMatch real work to do.

Cleaning applied while loading (same rules as the Pig job): only TMAX/TMIN/PRCP/SNOW/SNWD,
drop non-empty Q_FLAG (failed QC) and -9999 (missing); convert tenths of deg C / tenths of mm.

The file is sorted by date, so rows of one day are contiguous: we buffer a single day, group by
station, and insert in batches with insert_many(ordered=False). Secondary indexes are NOT created
here - profile_queries.py measures the queries before and after creating them.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import time

from pymongo import MongoClient
from tqdm import tqdm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = {"TMAX", "TMIN", "PRCP", "SNOW", "SNWD"}
TENTHS = {"TMAX", "TMIN", "PRCP"}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--years", default=os.environ.get("MONGO_YEARS", "2025"))
    p.add_argument("--exclude-prefix", default=os.environ.get("MONGO_EXCLUDE_PREFIX", "US1"))
    p.add_argument("--batch", type=int, default=10000)
    p.add_argument("--keep", action="store_true", help="do not drop existing collections")
    p.add_argument("--uri", default=f"mongodb://{os.environ.get('MONGO_HOST', 'localhost')}:"
                                    f"{os.environ.get('MONGO_PORT', '27017')}")
    return p.parse_args()


def load_stations(db):
    docs = []
    with open(os.path.join(ROOT, "data", "stations.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["_id"] = d["station_id"]
            docs.append(d)
    db.stations.drop()
    db.stations.insert_many(docs, ordered=False)
    print(f"stations: inserted {len(docs):,} documents into ghcn.stations")

    countries = []
    with open(os.path.join(ROOT, "data", "countries.tsv"), encoding="utf-8") as f:
        for line in f:
            code, name = line.rstrip("\n").split("\t", 1)
            countries.append({"_id": code, "name": name})
    db.countries.drop()
    db.countries.insert_many(countries)
    print(f"countries: inserted {len(countries)} documents into ghcn.countries")


def day_docs(rows):
    """rows: list of split CSV rows for ONE date -> station-day documents"""
    by_station = {}
    for p in rows:
        by_station.setdefault(p[0], []).append(p)
    date_s = rows[0][1]
    d = dt.datetime(int(date_s[:4]), int(date_s[4:6]), int(date_s[6:8]))
    for sid, ps in by_station.items():
        readings = []
        for p in ps:
            v = int(p[3])
            readings.append({
                "element": p[2],
                "value": v / 10.0 if p[2] in TENTHS else float(v),
                "m_flag": p[4],
                "s_flag": p[6],
            })
        yield {"station_id": sid, "country_code": sid[:2], "date": d,
               "year": d.year, "month": d.month, "day": d.day, "readings": readings}


def main():
    a = parse_args()
    years = [y.strip() for y in a.years.split(",") if y.strip()]
    excl = tuple(x.strip() for x in a.exclude_prefix.split(",") if x.strip())
    client = MongoClient(a.uri)
    db = client.ghcn
    print(f"MongoDB {client.server_info()['version']} at {a.uri}; years={years} exclude={excl or 'none'}")

    load_stations(db)
    if not a.keep:
        db.observations.drop()
    coll = db.observations

    stats = {"rows": 0, "kept_rows": 0, "qc_failed": 0, "missing": 0, "other_element": 0,
             "excluded_prefix": 0, "documents": 0}
    t0 = time.time()
    batch = []

    def flush():
        if batch:
            coll.insert_many(batch, ordered=False)
            stats["documents"] += len(batch)
            batch.clear()

    for y in years:
        path = os.path.join(ROOT, "data", "raw", f"{y}.csv.gz")
        size = os.path.getsize(path)
        with open(path, "rb") as raw_f, gzip.open(raw_f, "rt", encoding="ascii", errors="replace") as f, \
                tqdm(total=size, unit="B", unit_scale=True, desc=f"{y}.csv.gz", mininterval=5) as bar:
            day, cur_date, last_pos = [], None, 0
            for i, line in enumerate(f):
                stats["rows"] += 1
                p = line.rstrip("\n").split(",")
                if p[2] not in CORE:
                    stats["other_element"] += 1
                    continue
                if p[5]:
                    stats["qc_failed"] += 1
                    continue
                if p[3] == "-9999" or not p[3]:
                    stats["missing"] += 1
                    continue
                if excl and p[0].startswith(excl):
                    stats["excluded_prefix"] += 1
                    continue
                if p[1] != cur_date:
                    if day:
                        batch.extend(day_docs(day))
                        if len(batch) >= a.batch:
                            flush()
                    day, cur_date = [], p[1]
                day.append(p)
                stats["kept_rows"] += 1
                if i % 200000 == 0:
                    pos = raw_f.tell()
                    bar.update(pos - last_pos)
                    last_pos = pos
            if day:
                batch.extend(day_docs(day))
            flush()
            bar.update(size - last_pos)

    stats["seconds"] = round(time.time() - t0, 1)
    stats["docs_per_second"] = round(stats["documents"] / max(stats["seconds"], 1))
    cs = db.command("collStats", "observations")
    stats["data_size_mb"] = round(cs["size"] / 2**20, 1)
    stats["storage_size_mb"] = round(cs["storageSize"] / 2**20, 1)
    stats["avg_doc_bytes"] = cs.get("avgObjSize")
    print(json.dumps(stats, indent=2))
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "mongo_ingest_stats.json"), "w") as f:
        json.dump({"years": years, "exclude_prefix": list(excl), **stats}, f, indent=2)


if __name__ == "__main__":
    main()
