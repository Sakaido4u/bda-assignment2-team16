#!/usr/bin/env python3
"""Ask the JobHistory REST API which node every map/reduce attempt of a job ran on.

usage: python3 task_nodes.py <job_id> [<job_id> ...]
Appends rows to results/mr_task_nodes.csv and prints a per-node summary.
Runs inside the master container (stdlib only).
"""
import collections
import csv
import json
import os
import sys
import urllib.request

HIST = os.environ.get("JOBHISTORY_URL", "http://master:19888/ws/v1/history/mapreduce")
OUT = "/project/results/mr_task_nodes.csv"


def get(path):
    with urllib.request.urlopen(f"{HIST}{path}", timeout=30) as r:
        return json.load(r)


def main(job_ids):
    new = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["job_id", "job_name", "task_id", "type", "node", "elapsed_ms"])
        for jid in job_ids:
            job = get(f"/jobs/{jid}")["job"]
            tasks = get(f"/jobs/{jid}/tasks")["tasks"]["task"]
            per_node = collections.Counter()
            for t in tasks:
                attempts = get(f"/jobs/{jid}/tasks/{t['id']}/attempts")["taskAttempts"]["taskAttempt"]
                ok = [a for a in attempts if a.get("state") == "SUCCEEDED"] or attempts
                node = ok[-1]["nodeHttpAddress"].split(":")[0]
                per_node[(node, t["type"])] += 1
                w.writerow([jid, job["name"], t["id"], t["type"], node, t["elapsedTime"]])
            print(f"\n{jid}  {job['name']}")
            print(f"  maps={job['mapsTotal']} reduces={job['reducesTotal']} state={job['state']} "
                  f"elapsed={(job['finishTime'] - job['startTime']) / 1000:.1f}s")
            for (node, typ), n in sorted(per_node.items()):
                print(f"  {node:10s} {typ:7s} tasks: {n}")


if __name__ == "__main__":
    main(sys.argv[1:])
