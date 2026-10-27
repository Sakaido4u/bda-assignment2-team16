#!/usr/bin/env python3
"""Profile the downloaded GHCN-Daily subset for the report's Dataset Description section.

Streams every data/raw/YYYY.csv.gz once and writes results/dataset_stats.csv + .json with:
records, QC-failed records, records per element, distinct stations and countries, file sizes.
"""
import collections
import csv
import glob
import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
RES = os.path.join(ROOT, "results")
CORE = {"TMAX", "TMIN", "PRCP", "SNOW", "SNWD"}


def main():
    os.makedirs(RES, exist_ok=True)
    rows, summary = [], {}
    all_stations, all_countries = set(), set()
    total_elements = collections.Counter()
    for path in sorted(glob.glob(os.path.join(RAW, "[12][0-9][0-9][0-9].csv.gz"))):
        year = os.path.basename(path)[:4]
        n = qc_failed = core = 0
        stations = set()
        elements = collections.Counter()
        uncompressed = 0
        with gzip.open(path, "rt", encoding="ascii", errors="replace") as f:
            for line in f:
                uncompressed += len(line)
                p = line.split(",")
                n += 1
                stations.add(p[0])
                elements[p[2]] += 1
                if p[2] in CORE:
                    core += 1
                if p[5]:
                    qc_failed += 1
        countries = {s[:2] for s in stations}
        all_stations |= stations
        all_countries |= countries
        total_elements.update(elements)
        rows.append({
            "year": year,
            "records": n,
            "core_element_records": core,
            "qc_failed_records": qc_failed,
            "distinct_elements": len(elements),
            "stations": len(stations),
            "countries": len(countries),
            "compressed_mb": round(os.path.getsize(path) / 2**20, 1),
            "uncompressed_mb": round(uncompressed / 2**20, 1),
            **{f"n_{e}": elements.get(e, 0) for e in sorted(CORE)},
        })
        print(rows[-1], flush=True)

    with open(os.path.join(RES, "dataset_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "years": [r["year"] for r in rows],
        "total_records": sum(r["records"] for r in rows),
        "total_core_records": sum(r["core_element_records"] for r in rows),
        "total_qc_failed": sum(r["qc_failed_records"] for r in rows),
        "distinct_stations": len(all_stations),
        "distinct_countries": len(all_countries),
        "compressed_mb": round(sum(r["compressed_mb"] for r in rows), 1),
        "uncompressed_mb": round(sum(r["uncompressed_mb"] for r in rows), 1),
        "top_elements": total_elements.most_common(15),
    }
    with open(os.path.join(RES, "dataset_stats.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
