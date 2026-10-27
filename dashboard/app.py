"""Part 2 - GHCN-Daily Big Data dashboard (Flask).

Pages
  /             Cluster overview  (NameNode JMX + YARN ResourceManager REST, live)
  /climate      Climate analytics (MongoDB aggregation results, Chart.js)
  /map          Station map       (MongoDB 2dsphere $geoNear, Leaflet)
  /hive         Hive queries      (predefined, parameterised HQL through HiveServer2 / PyHive)
  /performance  Part 1 results    (MongoDB index profiling, Hive TEXTFILE vs RCFile, MapReduce)
"""
import csv
import datetime as dt
import json
import os
import re
import time

import requests
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MASTER = os.environ.get("MASTER_HOST", "master")
NAMENODE = os.environ.get("NAMENODE_URL", f"http://{MASTER}:9870")
RM = os.environ.get("RM_URL", f"http://{MASTER}:8088")
HIVE_HOST = os.environ.get("HIVE_HOST", MASTER)
MONGO_URI = f"mongodb://{os.environ.get('MONGO_HOST', 'mongodb')}:{os.environ.get('MONGO_PORT', '27017')}"
RESULTS = os.environ.get("RESULTS_DIR", "/app/results")

app = Flask(__name__)
mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = mongo.ghcn


class ServiceDown(Exception):
    pass


@app.errorhandler(ServiceDown)
def service_down(e):
    return jsonify({"error": str(e)}), 503


@app.errorhandler(PyMongoError)
def mongo_down(e):
    return jsonify({"error": f"MongoDB unavailable: {e.__class__.__name__}: {str(e)[:200]}"}), 503


def get_json(url, what):
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001 - any failure means the service is unreachable
        raise ServiceDown(f"{what} unreachable ({url}): {e.__class__.__name__}")


# ------------------------------------------------------------------ pages
@app.route("/")
def overview():
    return render_template("overview.html", page="overview")


@app.route("/climate")
def climate():
    return render_template("climate.html", page="climate")


@app.route("/map")
def station_map():
    return render_template("map.html", page="map")


@app.route("/hive")
def hive_page():
    return render_template("hive.html", page="hive", queries=HIVE_QUERIES)


@app.route("/performance")
def performance():
    return render_template("performance.html", page="performance")


# ------------------------------------------------------------------ 1. cluster
@app.route("/api/cluster")
def api_cluster():
    out = {"errors": []}
    try:
        jmx = get_json(f"{NAMENODE}/jmx?qry=Hadoop:service=NameNode,name=NameNodeInfo", "NameNode")["beans"][0]
        fs = get_json(f"{NAMENODE}/jmx?qry=Hadoop:service=NameNode,name=FSNamesystemState", "NameNode")["beans"][0]
        nodes = []
        for name, n in json.loads(jmx["LiveNodes"]).items():
            nodes.append({
                "name": name.split(":")[0], "address": n.get("xferaddr"),
                "used_gb": round(n["used"] / 2**30, 2), "capacity_gb": round(n["capacity"] / 2**30, 1),
                "remaining_gb": round(n["remaining"] / 2**30, 1), "blocks": n.get("numBlocks"),
                "last_contact_s": n.get("lastContact"), "state": n.get("adminState"),
            })
        out["hdfs"] = {
            "live_datanodes": fs["NumLiveDataNodes"], "dead_datanodes": fs["NumDeadDataNodes"],
            "capacity_gb": round(fs["CapacityTotal"] / 2**30, 1), "used_gb": round(fs["CapacityUsed"] / 2**30, 2),
            "files": fs["FilesTotal"], "blocks": fs["BlocksTotal"], "under_replicated": fs["UnderReplicatedBlocks"],
            "version": jmx["Version"].split(",")[0], "safemode": jmx["Safemode"] or "OFF",
            "datanodes": sorted(nodes, key=lambda x: x["name"]),
        }
    except ServiceDown as e:
        out["errors"].append(str(e))
    except (IndexError, KeyError, ValueError):
        out["errors"].append("NameNode is starting up (JMX metrics not available yet)")
    try:
        info = get_json(f"{RM}/ws/v1/cluster/info", "ResourceManager")["clusterInfo"]
        metrics = get_json(f"{RM}/ws/v1/cluster/metrics", "ResourceManager")["clusterMetrics"]
        nodes = (get_json(f"{RM}/ws/v1/cluster/nodes", "ResourceManager").get("nodes") or {}).get("node", [])
        # after a NodeManager restart the RM keeps the old (SHUTDOWN) entry next to the new one: keep the RUNNING one
        nodes = sorted(nodes, key=lambda n: n["state"] == "RUNNING")
        nodes = list({n["nodeHostName"]: n for n in nodes}.values())
        apps = (get_json(f"{RM}/ws/v1/cluster/apps", "ResourceManager").get("apps") or {}).get("app", [])
        apps = sorted(apps, key=lambda a: a["startedTime"], reverse=True)[:12]
        out["yarn"] = {
            "state": info["state"], "version": info["hadoopVersion"],
            "active_nodes": metrics["activeNodes"], "lost_nodes": metrics["lostNodes"],
            "unhealthy_nodes": metrics["unhealthyNodes"],
            "memory_total_mb": metrics["totalMB"], "memory_used_mb": metrics["allocatedMB"],
            "vcores_total": metrics["totalVirtualCores"], "containers": metrics["containersAllocated"],
            "apps_completed": metrics["appsCompleted"], "apps_running": metrics["appsRunning"],
            "apps_failed": metrics["appsFailed"],
            "nodes": [{"id": n["id"], "host": n["nodeHostName"], "state": n["state"],
                       "containers": n["numContainers"], "used_mb": n["usedMemoryMB"],
                       "avail_mb": n["availMemoryMB"], "health": n.get("healthReport") or "healthy",
                       "last_heartbeat": dt.datetime.fromtimestamp(n["lastHealthUpdate"] / 1000).strftime("%H:%M:%S")}
                      for n in sorted(nodes, key=lambda n: n["nodeHostName"])],
            "apps": [{"id": a["id"], "name": a["name"][:80], "type": a["applicationType"], "state": a["state"],
                      "final": a["finalStatus"], "progress": round(a["progress"]),
                      "elapsed_s": round(a["elapsedTime"] / 1000), "started": dt.datetime.fromtimestamp(
                          a["startedTime"] / 1000).strftime("%d %b %H:%M")} for a in apps],
        }
    except ServiceDown as e:
        out["errors"].append(str(e))
    except (IndexError, KeyError, ValueError):
        out["errors"].append("ResourceManager is starting up (metrics not available yet)")
    try:
        mongo.admin.command("ping")
        out["mongo"] = {"ok": True, "observations": db.observations.estimated_document_count(),
                        "stations": db.stations.estimated_document_count()}
    except PyMongoError as e:
        out["errors"].append(f"MongoDB unreachable: {e.__class__.__name__}")
    return jsonify(out)


# ------------------------------------------------------------------ 2. climate (MongoDB)
def ensure_summary():
    """summary_country_month is materialised once from observations with a MongoDB $merge pipeline."""
    if db.summary_country_month.estimated_document_count() == 0:
        raise ServiceDown("summary collection missing - run: docker compose run --rm tools python mongodb/build_summaries.py")


@app.route("/api/climate/countries")
def api_countries():
    ensure_summary()
    rows = db.summary_country_month.aggregate([
        {"$match": {"element": "TMAX"}},
        {"$group": {"_id": "$country_code", "name": {"$first": "$country_name"}, "n": {"$sum": "$n"}}},
        {"$match": {"n": {"$gte": 1000}}},
        {"$sort": {"name": 1}}])
    return jsonify([{"code": r["_id"], "name": r["name"], "n": r["n"]} for r in rows])


def country_arg():
    c = request.args.get("country", "IN")
    if not re.fullmatch(r"[A-Z]{2}", c):
        raise ServiceDown("invalid country code")
    return c


@app.route("/api/climate/country")
def api_country_climate():
    ensure_summary()
    c = country_arg()
    docs = list(db.summary_country_month.find({"country_code": c}, {"_id": 0}).sort([("year", 1), ("month", 1)]))
    if not docs:
        return jsonify({"error": f"no data for {c}"}), 404
    by_year, monthly = {}, {}
    for d in docs:
        y = by_year.setdefault(d["year"], {"TMAX": [0, 0], "TMIN": [0, 0], "PRCP": 0, "heat_days": 0, "PRCP_n": 0})
        if d["element"] in ("TMAX", "TMIN"):
            y[d["element"]][0] += d["sum"]
            y[d["element"]][1] += d["n"]
        if d["element"] == "TMAX":
            y["heat_days"] += d.get("over_40", 0)
        if d["element"] == "PRCP":
            y["PRCP_n"] += d["n"]
            m = monthly.setdefault(d["year"], [None] * 12)
            m[d["month"] - 1] = round(d["avg"], 2)
    years = sorted(by_year)
    return jsonify({
        "country": c, "name": docs[0].get("country_name"), "years": years,
        "avg_tmax": [round(by_year[y]["TMAX"][0] / by_year[y]["TMAX"][1], 2) if by_year[y]["TMAX"][1] else None for y in years],
        "avg_tmin": [round(by_year[y]["TMIN"][0] / by_year[y]["TMIN"][1], 2) if by_year[y]["TMIN"][1] else None for y in years],
        "heat_days": [by_year[y]["heat_days"] for y in years],
        "monthly_prcp_avg": {str(y): monthly.get(y, [None] * 12) for y in years},
        "monthly_tmax": {str(y): [next((round(d["avg"], 2) for d in docs if d["year"] == y and d["month"] == m and d["element"] == "TMAX"), None)
                                  for m in range(1, 13)] for y in years},
    })


@app.route("/api/climate/global_heat")
def api_global_heat():
    ensure_summary()
    rows = db.summary_country_month.aggregate([
        {"$match": {"element": "TMAX"}},
        {"$group": {"_id": {"c": "$country_code", "name": "$country_name"}, "heat_days": {"$sum": "$over_40"}}},
        {"$match": {"heat_days": {"$gt": 0}}},
        {"$sort": {"heat_days": -1}}, {"$limit": 15}])
    return jsonify([{"code": r["_id"]["c"], "name": r["_id"]["name"], "heat_days": r["heat_days"]} for r in rows])


# ------------------------------------------------------------------ 3. station map (2dsphere)
@app.route("/api/stations/near")
def api_near():
    try:
        lat = float(request.args.get("lat", 12.9716))
        lon = float(request.args.get("lon", 77.5946))
        km = min(float(request.args.get("km", 200)), 1000)
    except ValueError:
        return jsonify({"error": "lat, lon and km must be numbers"}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "coordinates out of range"}), 400
    t0 = time.perf_counter()
    rows = list(db.stations.aggregate([
        {"$geoNear": {"near": {"type": "Point", "coordinates": [lon, lat]}, "distanceField": "dist_m",
                      "maxDistance": km * 1000, "spherical": True}},
        {"$limit": 500},
        {"$project": {"_id": 0, "station_id": 1, "name": 1, "latitude": 1, "longitude": 1,
                      "elevation": 1, "country_name": 1, "dist_km": {"$round": [{"$divide": ["$dist_m", 1000]}, 1]}}}]))
    return jsonify({"stations": rows, "ms": round((time.perf_counter() - t0) * 1000, 1)})


@app.route("/api/station/<sid>")
def api_station(sid):
    if not re.fullmatch(r"[A-Z0-9]{11}", sid):
        return jsonify({"error": "invalid station id"}), 400
    st = db.stations.find_one({"_id": sid}, {"_id": 0, "location": 0})
    if not st:
        return jsonify({"error": "unknown station"}), 404
    t0 = time.perf_counter()
    summary = list(db.observations.aggregate([
        {"$match": {"station_id": sid}},
        {"$unwind": "$readings"},
        {"$group": {"_id": "$readings.element", "avg": {"$avg": "$readings.value"}, "min": {"$min": "$readings.value"},
                    "max": {"$max": "$readings.value"}, "n": {"$sum": 1}, "first": {"$min": "$date"},
                    "last": {"$max": "$date"}}},
        {"$sort": {"_id": 1}}]))
    for s in summary:
        s["element"] = s.pop("_id")
        s["avg"] = round(s["avg"], 2)
        s["first"] = s["first"].strftime("%Y-%m-%d")
        s["last"] = s["last"].strftime("%Y-%m-%d")
    return jsonify({"station": st, "summary": summary, "ms": round((time.perf_counter() - t0) * 1000, 1)})


# ------------------------------------------------------------------ 4. Hive (predefined only)
ELEMENTS = ["TMAX", "TMIN", "PRCP", "SNOW", "SNWD"]
YEARS = [2023, 2024, 2025]
HIVE_QUERIES = {
    "country_monthly": {
        "title": "Monthly averages for a country, element and year",
        "table": "monthly_summary (RCFile)",
        "params": ["country", "element", "year"],
        "sql": "SELECT month, avg_value, min_value, max_value, n_obs, n_stations FROM monthly_summary "
               "WHERE country_code = %(country)s AND element = %(element)s AND year = %(year)s ORDER BY month",
    },
    "top_countries": {
        "title": "Top N countries by yearly average of an element",
        "table": "monthly_summary (RCFile)",
        "params": ["element", "year", "limit"],
        "sql": "SELECT country_code, country_name, ROUND(SUM(avg_value * n_obs) / SUM(n_obs), 2) AS yearly_avg, "
               "SUM(n_obs) AS n_obs FROM monthly_summary WHERE element = %(element)s AND year = %(year)s "
               "GROUP BY country_code, country_name HAVING SUM(n_obs) > 3000 ORDER BY yearly_avg DESC LIMIT %(limit)d",
    },
    "element_counts": {
        "title": "Observation counts per element and year",
        "table": "monthly_summary (RCFile)",
        "params": [],
        "sql": "SELECT year, element, SUM(n_obs) AS observations FROM monthly_summary GROUP BY year, element ORDER BY year, element",
    },
    "hottest_stations": {
        "title": "Hottest stations of a country in a year (full scan of obs_rc + join, ~1-3 min)",
        "table": "obs_rc (RCFile, ~80M rows) JOIN stations",
        "params": ["country", "year", "limit"],
        "sql": "SELECT s.name, s.latitude, s.longitude, ROUND(AVG(o.value), 2) AS avg_tmax, MAX(o.value) AS max_tmax, "
               "COUNT(*) AS days FROM obs_rc o JOIN stations s ON (o.station_id = s.station_id) "
               "WHERE o.country_code = %(country)s AND o.year = %(year)s AND o.element = 'TMAX' "
               "GROUP BY s.name, s.latitude, s.longitude HAVING COUNT(*) > 200 ORDER BY avg_tmax DESC LIMIT %(limit)d",
    },
}


def hive_params(spec):
    p = {}
    for name in spec["params"]:
        v = request.json.get(name) if request.is_json else None
        if name == "country":
            if not (isinstance(v, str) and re.fullmatch(r"[A-Z]{2}", v)):
                raise ValueError("country must be a 2-letter code")
            p[name] = v
        elif name == "element":
            if v not in ELEMENTS:
                raise ValueError(f"element must be one of {ELEMENTS}")
            p[name] = v
        elif name == "year":
            if int(v) not in YEARS:
                raise ValueError(f"year must be one of {YEARS}")
            p[name] = int(v)
        elif name == "limit":
            p[name] = max(1, min(int(v), 50))
    return p


@app.route("/api/hive/<qid>", methods=["POST"])
def api_hive(qid):
    spec = HIVE_QUERIES.get(qid)
    if not spec:
        return jsonify({"error": "unknown query"}), 404
    try:
        params = hive_params(spec)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    try:
        from pyhive import hive
        t0 = time.perf_counter()
        conn = hive.Connection(host=HIVE_HOST, port=10000, username="root", database="ghcn")
        cur = conn.cursor()
        cur.execute(spec["sql"], params)       # PyHive escapes the (already whitelisted) parameters
        rows = cur.fetchall()
        cols = [d[0].split(".")[-1] for d in cur.description]
        conn.close()
        return jsonify({"columns": cols, "rows": rows, "seconds": round(time.perf_counter() - t0, 2),
                        "sql": spec["sql"] % {k: (f"'{v}'" if isinstance(v, str) else v) for k, v in params.items()}})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"HiveServer2 error: {e.__class__.__name__}: {str(e)[:300]}"}), 503


# ------------------------------------------------------------------ 5. performance (Part 1 CSVs)
def read_csv(name):
    path = os.path.join(RESULTS, name)
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@app.route("/api/performance")
def api_performance():
    return jsonify({
        "mongo": read_csv("mongo_profile.csv"),
        "hive": read_csv("hive_benchmark_summary.csv"),
        "hive_storage": read_csv("hive_storage.csv"),
        "mapreduce": read_csv("mapreduce_times.csv"),
    })


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
