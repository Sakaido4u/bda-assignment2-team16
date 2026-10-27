#!/usr/bin/env python3
"""Hadoop Streaming reducer: final avg TMAX / TMIN (deg C) per country-year.
Output: country \t year \t avg_tmax \t avg_tmin \t n_tmax \t n_tmin  (same as the Java job)
"""
import sys


def emit(key, a):
    country, year = key.split("|")
    tmax = f"{a[0] / 10.0 / a[1]:.2f}" if a[1] else "NaN"
    tmin = f"{a[2] / 10.0 / a[3]:.2f}" if a[3] else "NaN"
    print(f"{country}\t{year}\t{tmax}\t{tmin}\t{a[1]}\t{a[3]}")


cur, acc = None, [0, 0, 0, 0]
for line in sys.stdin:
    key, val = line.rstrip("\n").split("\t", 1)
    nums = [int(x) for x in val.split(",")]
    if key != cur:
        if cur is not None:
            emit(cur, acc)
        cur, acc = key, [0, 0, 0, 0]
    for i in range(4):
        acc[i] += nums[i]
if cur is not None:
    emit(cur, acc)
