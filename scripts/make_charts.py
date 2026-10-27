#!/usr/bin/env python3
"""Builds the report charts (PNG) from the CSV/JSON results in results/.

  docker compose run --rm tools python scripts/make_charts.py
Every chart is skipped quietly if its input file does not exist yet.
"""
import csv
import json
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
OUT = os.path.join(RES, "charts")
os.makedirs(OUT, exist_ok=True)

# validated categorical order (fixed, never cycled); text uses ink colours, not series colours
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e6e3"
# colour follows the entity: each Hive table keeps its colour in every chart
TABLE_ORDER = ["obs_text", "obs_rc", "obs_rc_snappy", "obs_orc"]
TABLE_COLOR = {"obs_text": C[1], "obs_rc": C[0], "obs_rc_snappy": C[2], "obs_orc": C[3]}
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK,
    "axes.titleweight": "bold", "axes.titlesize": 11, "axes.grid": True, "grid.color": GRID,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "figure.facecolor": "white",
})


def rows(name):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        return None
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), bbox_inches="tight")
    plt.close(fig)
    print("chart:", name)


def grouped_bars(ax, labels, series, colors, fmt="{:.0f}", log=False):
    n = len(series)
    w = 0.8 / n
    for i, (name, vals) in enumerate(series):
        xs = [x + (i - (n - 1) / 2) * w for x in range(len(labels))]
        bars = ax.bar(xs, vals, w * 0.92, label=name, color=colors[i], edgecolor="white", linewidth=1)
        for b, v in zip(bars, vals):
            if v:
                ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                            ha="center", va="bottom", fontsize=7, color=INK2, xytext=(0, 2), textcoords="offset points")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=0)
    if log:
        ax.set_yscale("log")
    ax.legend()


def dataset():
    r = rows("dataset_stats.csv")
    if not r:
        return
    els = ["PRCP", "SNOW", "TMAX", "TMIN", "SNWD"]
    fig, ax = plt.subplots(figsize=(8, 4))
    grouped_bars(ax, els, [(x["year"], [int(x[f"n_{e}"]) / 1e6 for e in els]) for x in r], C, fmt="{:.1f}")
    ax.set_ylabel("records (millions)")
    ax.set_title("GHCN-Daily core-element records per year")
    save(fig, "dataset_elements.png")


def mongo():
    r = rows("mongo_profile.csv")
    if not r:
        return
    qs = list(dict.fromkeys(x["query"] for x in r))
    lab = [q.split("_", 1)[1].replace("_", "\n") for q in qs]
    get = lambda ph, col: [float(next(x for x in r if x["query"] == q and x["phase"] == ph)[col] or 0) for q in qs]  # noqa: E731
    for col, name, ylabel, title in (
            ("wall_ms_avg", "mongo_profile_time.png", "avg time (ms, log scale)", "MongoDB query time before vs after indexing"),
            ("totalDocsExamined", "mongo_profile_docs.png", "documents examined (log scale)", "MongoDB documents examined before vs after indexing")):
        fig, ax = plt.subplots(figsize=(10, 4.4))
        b, a = get("before", col), get("after", col)
        grouped_bars(ax, lab, [("before (only _id index)", [max(v, 0.5) for v in b]),
                               ("after (secondary indexes)", [max(v, 0.5) for v in a])], [C[1], C[0]], log=True)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        save(fig, name)


def hive():
    r = rows("hive_benchmark_summary.csv")
    if r:
        tables = [t for t in TABLE_ORDER if any(x["table"] == t for x in r)]
        qs = sorted(set(x["query"] for x in r))
        for col, name, ylabel, title, f in (
                ("avg_seconds", "hive_query_time.png", "average of 3 runs (s)", "Hive query time: TEXTFILE vs RCFile", "{:.0f}"),
                ("avg_hdfs_mb_read", "hive_hdfs_read.png", "HDFS bytes read (MB)", "Hive data read from HDFS per query", "{:.0f}")):
            fig, ax = plt.subplots(figsize=(10, 4.4))
            series = [(t, [float(next((x[col] for x in r if x["table"] == t and x["query"] == q), 0) or 0) for q in qs]) for t in tables]
            grouped_bars(ax, qs, series, [TABLE_COLOR[t] for t in tables], fmt=f)
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            save(fig, name)
    s = rows("hive_storage.csv")
    if s:
        s = [next(x for x in s if x["table"] == t) for t in TABLE_ORDER if any(x["table"] == t for x in s)]
        fig, ax = plt.subplots(figsize=(7, 4))
        vals = [int(x["bytes"]) / 2**20 for x in s]
        bars = ax.bar([x["table"] for x in s], vals, 0.6, color=[TABLE_COLOR[x["table"]] for x in s], edgecolor="white")
        base = vals[0]
        for b_, v in zip(bars, vals):
            ax.annotate(f"{v:,.0f} MB\n({v / base:.2f}x)", (b_.get_x() + b_.get_width() / 2, v), ha="center",
                        va="bottom", fontsize=8, color=INK2, xytext=(0, 2), textcoords="offset points")
        ax.set_ylabel("size of one replica (MB)")
        ax.set_title("Hive table size by storage format")
        save(fig, "hive_storage.png")


def mapreduce():
    r = rows("mapreduce_times.csv")
    if r:
        fig, ax = plt.subplots(figsize=(8, 3.2))
        labels = [f"{x['job'].replace('_', ' ')}\n({x['implementation'].replace('_', ' ')})" for x in r]
        vals = [float(x["wall_seconds"]) for x in r]
        bars = ax.barh(labels, vals, 0.55, color=[C[0] if x["implementation"] == "java" else C[1] for x in r])
        for b_, v in zip(bars, vals):
            ax.annotate(f"{v:.0f} s", (v, b_.get_y() + b_.get_height() / 2), va="center", xytext=(4, 0),
                        textcoords="offset points", fontsize=8, color=INK2)
        ax.invert_yaxis()
        ax.set_xlabel("wall-clock time (s), 3.8 GB input, 122 map tasks")
        ax.set_title("MapReduce on YARN: Java vs Python Streaming")
        save(fig, "mapreduce_times.png")
    t = rows("mr_task_nodes.csv")
    if t:
        cnt = defaultdict(lambda: defaultdict(int))
        for x in t:
            n = x["job_name"]
            label = ("Job 1 (Python Streaming)" if "Streaming" in n else "Job 1 (Java)" if "Job1" in n
                     else "Job 2 (Java)" if "Job2" in n else n[:25])
            cnt[label][x["node"]] += 1
        jobs = list(cnt)
        nodes = sorted({n for j in cnt.values() for n in j})
        fig, ax = plt.subplots(figsize=(9, 3.6))
        grouped_bars(ax, jobs,
                     [(n, [cnt[j][n] for j in jobs]) for n in nodes], C)
        ax.set_ylabel("map + reduce tasks")
        ax.set_title("Tasks executed per worker node (JobHistory API)")
        save(fig, "mr_task_nodes.png")
    tsv = os.path.join(ROOT, "mapreduce", "sample-output", "job1_country_temp_java.tsv")
    if os.path.exists(tsv):
        data = defaultdict(dict)
        for line in open(tsv):
            c, y, tmax, tmin, n1, n2 = line.rstrip("\n").split("\t")
            if tmax != "NaN" and int(n1) > 5000:
                data[c][y] = float(tmax)
        top = sorted(data, key=lambda c: -max(data[c].values()))[:12]
        years = sorted({y for c in top for y in data[c]})
        fig, ax = plt.subplots(figsize=(10, 4))
        grouped_bars(ax, top, [(y, [data[c].get(y, 0) for c in top]) for y in years], C, fmt="{:.0f}")
        ax.set_ylabel("average TMAX (°C)")
        ax.set_title("Hottest countries by average daily maximum (MapReduce Job 1, countries with >5000 readings)")
        save(fig, "mr_hottest_countries.png")


def pig():
    p = os.path.join(RES, "pig_clean_counts.tsv")
    if not os.path.exists(p):
        return
    stages = [ln.rstrip("\n").split("\t") for ln in open(p) if ln[0].isdigit()]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    labels = [s[0][2:].replace("_", " ") for s in stages]
    vals = [int(s[1]) / 1e6 for s in stages]
    bars = ax.barh(labels, vals, 0.55, color=[C[0], C[0], C[1], C[1], C[2]][:len(vals)])
    for b_, v in zip(bars, vals):
        ax.annotate(f"{v:,.2f} M", (v, b_.get_y() + b_.get_height() / 2), va="center", xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=INK2)
    ax.invert_yaxis()
    ax.set_xlabel("records (millions)")
    ax.set_title("Pig cleaning: records at each stage")
    save(fig, "pig_clean_funnel.png")


if __name__ == "__main__":
    for f in (dataset, mongo, hive, mapreduce, pig):
        f()
