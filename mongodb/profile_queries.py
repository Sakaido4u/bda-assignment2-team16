#!/usr/bin/env python3
"""Theme 1 - query profiling BEFORE and AFTER indexing.

  docker compose run --rm tools python mongodb/profile_queries.py

1. drops every secondary index (only _id remains)
2. runs each query with explain("executionStats") and times real executions (RUNS times)
3. creates the indexes: {station_id:1, date:1}, {"readings.element":1}, stations {location:"2dsphere"}
4. repeats step 2
Writes results/mongo_profile.csv and results/mongo_indexes.json.
"""
import csv
import datetime as dt
import json
import os
import statistics
import time

from pymongo import MongoClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = int(os.environ.get("PROFILE_RUNS", "3"))
STATION = "IN009010100"                       # BANGALORE (GSN)
BLR = [77.5946, 12.9716]                      # [lon, lat]

client = MongoClient(f"mongodb://{os.environ.get('MONGO_HOST', 'localhost')}:{os.environ.get('MONGO_PORT', '27017')}")
db = client.ghcn

# name -> (collection, kind, spec, description)
QUERIES = {
    "P1_station_monthly_prcp": ("observations", "aggregate", [
        {"$match": {"station_id": STATION}},
        {"$unwind": "$readings"},
        {"$match": {"readings.element": "PRCP"}},
        {"$group": {"_id": {"y": "$year", "m": "$month"}, "total_mm": {"$sum": "$readings.value"}}},
        {"$sort": {"_id": 1}}], "Monthly PRCP totals for one station ($match on station_id)"),
    "P2_station_date_range": ("observations", "find", {
        "station_id": STATION,
        "date": {"$gte": dt.datetime(2025, 1, 1), "$lt": dt.datetime(2025, 4, 1)}},
        "One station, one quarter (find on station_id + date range)"),
    "P3_india_hottest": ("observations", "aggregate", [
        {"$match": {"station_id": {"$regex": "^IN"}}},
        {"$unwind": "$readings"},
        {"$match": {"readings.element": "TMAX"}},
        {"$group": {"_id": "$station_id", "avg": {"$avg": "$readings.value"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 300}}},
        {"$sort": {"avg": -1}}, {"$limit": 10}], "Top-10 hottest Indian stations (anchored ^IN prefix)"),
    "P4_extreme_heat_days": ("observations", "aggregate", [
        {"$match": {"readings": {"$elemMatch": {"element": "TMAX", "value": {"$gt": 40}}}}},
        {"$unwind": "$readings"},
        {"$match": {"readings.element": "TMAX", "readings.value": {"$gt": 40}}},
        {"$group": {"_id": "$year", "days": {"$sum": 1}}},
        {"$sort": {"_id": 1}}], "Extreme-heat days per year ($elemMatch on readings.element)"),
    "P5_geo_200km_bengaluru": ("stations", "find", {
        "location": {"$geoWithin": {"$centerSphere": [BLR, 200 / 6378.1]}}},
        "Stations within 200 km of Bengaluru ($geoWithin)"),
    "P6_yearly_country_temp": ("observations", "aggregate", [
        {"$unwind": "$readings"},
        {"$match": {"readings.element": {"$in": ["TMAX", "TMIN"]}}},
        {"$group": {"_id": {"c": "$country_code", "y": "$year", "e": "$readings.element"},
                    "avg": {"$avg": "$readings.value"}}}],
        "Yearly avg TMAX/TMIN per country (full scan - control query)"),
}


def find_key(obj, key):
    """first value for `key` anywhere in a nested explain document"""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def stages(obj, acc):
    if isinstance(obj, dict):
        if "stage" in obj:
            acc.append(obj["stage"])
        for k, v in obj.items():
            if k != "rejectedPlans":
                stages(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            stages(v, acc)
    return acc


def plan_summary(explain):
    st = stages(find_key(explain, "winningPlan") or {}, [])
    for s in ("COLLSCAN", "GEO_NEAR_2DSPHERE", "IXSCAN"):
        if s in st:
            return s, ">".join(dict.fromkeys(st))
    return (st[-1] if st else "?"), ">".join(dict.fromkeys(st))


def run_once(coll, kind, spec):
    c = db[coll]
    if kind == "find":
        return len(list(c.find(spec)))
    return len(list(c.aggregate(spec, allowDiskUse=True)))


def explain(coll, kind, spec):
    if kind == "find":
        cmd = {"find": coll, "filter": spec}
    else:
        cmd = {"aggregate": coll, "pipeline": spec, "cursor": {}}
    return db.command("explain", cmd, verbosity="executionStats")


def profile(phase):
    rows = []
    for name, (coll, kind, spec, desc) in QUERIES.items():
        ex = explain(coll, kind, spec)
        es = find_key(ex, "executionStats") or {}
        stage, chain = plan_summary(ex)
        times = []
        for _ in range(RUNS):
            t0 = time.perf_counter()
            n = run_once(coll, kind, spec)
            times.append((time.perf_counter() - t0) * 1000)
        row = {
            "query": name, "description": desc, "phase": phase,
            "plan_stage": stage, "plan_chain": chain,
            "executionTimeMillis": es.get("executionTimeMillis", ""),
            "totalKeysExamined": es.get("totalKeysExamined", ""),
            "totalDocsExamined": es.get("totalDocsExamined", ""),
            "nReturned_explain": es.get("nReturned", ""),
            "result_rows": n,
            "wall_ms_avg": round(statistics.mean(times), 1),
            "wall_ms_min": round(min(times), 1),
        }
        print(f"[{phase:6s}] {name:26s} {stage:18s} exec={row['executionTimeMillis']}ms "
              f"keys={row['totalKeysExamined']} docs={row['totalDocsExamined']} wall={row['wall_ms_avg']}ms",
              flush=True)
        rows.append(row)
    return rows


def drop_secondary():
    for coll in ("observations", "stations"):
        for ix in db[coll].list_indexes():
            if ix["name"] != "_id_":
                db[coll].drop_index(ix["name"])


def create_indexes():
    t = {}
    for coll, keys, name in (("observations", [("station_id", 1), ("date", 1)], "station_date"),
                             ("observations", [("readings.element", 1)], "element"),
                             ("stations", [("location", "2dsphere")], "location_2dsphere")):
        t0 = time.time()
        db[coll].create_index(keys, name=name)
        t[name] = round(time.time() - t0, 1)
        print(f"created index {coll}.{name} in {t[name]} s", flush=True)
    return t


def main():
    print(f"observations={db.observations.estimated_document_count():,} stations={db.stations.estimated_document_count():,}")
    drop_secondary()
    before = profile("before")
    build_times = create_indexes()
    after = profile("after")

    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "mongo_profile.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(before[0].keys()))
        w.writeheader()
        w.writerows(before + after)
    stats = db.command("collStats", "observations")
    info = {
        "observations_indexes": list(db.observations.index_information().items()),
        "stations_indexes": list(db.stations.index_information().items()),
        "index_build_seconds": build_times,
        "index_sizes_mb": {k: round(v / 2**20, 1) for k, v in stats["indexSizes"].items()},
        "stations_index_sizes_mb": {k: round(v / 2**20, 2) for k, v in db.command("collStats", "stations")["indexSizes"].items()},
    }
    with open(os.path.join(ROOT, "results", "mongo_indexes.json"), "w") as f:
        json.dump(info, f, indent=2, default=str)
    print(json.dumps(info["index_sizes_mb"], indent=2))


if __name__ == "__main__":
    main()
