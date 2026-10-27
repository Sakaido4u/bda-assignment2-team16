#!/usr/bin/env python3
"""Joins each benchmark run (results/hive_runs_raw.csv) with the MapReduce jobs it launched
(JobHistory REST API, matched by start-time window) and writes:
  results/hive_benchmark.csv          one row per run, with HDFS bytes read / maps / CPU
  results/hive_benchmark_summary.csv  average per (table, query) and RCFile-vs-TEXTFILE speed-up
Standard library only (runs in the master container).
"""
import collections
import csv
import json
import urllib.request

HIST = "http://master:19888/ws/v1/history/mapreduce"
RAW = "/project/results/hive_runs_raw.csv"


def get(path):
    with urllib.request.urlopen(HIST + path, timeout=60) as r:
        return json.load(r)


def counters(job_id):
    groups = get(f"/jobs/{job_id}/counters")["jobCounters"].get("counterGroup", [])
    flat = {}
    for g in groups:
        for c in g.get("counter", []):
            flat[c["name"]] = c["totalCounterValue"]
    return flat


def main():
    runs = list(csv.DictReader(open(RAW)))
    for r in runs:
        r["query"] = r["query"].lstrip("@")
    if not runs:
        print("no runs recorded")
        return
    t_min = min(int(r["t0_ms"]) for r in runs) - 1000
    jobs = get(f"/jobs?startedTimeBegin={t_min}").get("jobs") or {}
    jobs = jobs.get("job", [])
    print(f"{len(jobs)} MapReduce jobs found in JobHistory for the benchmark window")

    rows = []
    for r in runs:
        t0, t1 = int(r["t0_ms"]), int(r["t1_ms"])
        mine = [j for j in jobs if t0 <= j["startTime"] <= t1]
        hbr = maps = reduces = cpu = 0
        for j in mine:
            c = counters(j["id"])
            hbr += c.get("HDFS_BYTES_READ", 0)
            cpu += c.get("CPU_MILLISECONDS", 0)
            maps += j["mapsTotal"]
            reduces += j["reducesTotal"]
        rows.append({**{k: r[k] for k in ("table", "query", "run", "seconds", "rows")},
                     "mr_jobs": len(mine), "maps": maps, "reduces": reduces,
                     "hdfs_bytes_read": hbr, "cpu_ms": cpu})

    with open("/project/results/hive_benchmark.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    agg = collections.defaultdict(list)
    for r in rows:
        agg[(r["table"], r["query"])].append(r)
    summary = []
    for (tbl, q), rs in sorted(agg.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        summary.append({
            "query": q, "table": tbl, "runs": len(rs),
            "avg_seconds": round(sum(float(x["seconds"]) for x in rs) / len(rs), 2),
            "min_seconds": min(float(x["seconds"]) for x in rs),
            "max_seconds": max(float(x["seconds"]) for x in rs),
            "avg_hdfs_mb_read": round(sum(x["hdfs_bytes_read"] for x in rs) / len(rs) / 2**20, 1),
            "maps": rs[0]["maps"], "reduces": rs[0]["reduces"],
            "avg_cpu_s": round(sum(x["cpu_ms"] for x in rs) / len(rs) / 1000, 1),
        })
    base = {s["query"]: s for s in summary if s["table"] == "obs_text"}
    for s in summary:
        b = base.get(s["query"])
        s["speedup_vs_text"] = round(b["avg_seconds"] / s["avg_seconds"], 2) if b and s["avg_seconds"] else ""
        s["read_reduction_vs_text_pct"] = (round(100 * (1 - s["avg_hdfs_mb_read"] / b["avg_hdfs_mb_read"]), 1)
                                           if b and b["avg_hdfs_mb_read"] else "")
    with open("/project/results/hive_benchmark_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
