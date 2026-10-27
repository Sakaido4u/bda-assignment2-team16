#!/usr/bin/env python3
"""Hadoop Streaming mapper - same logic as Java Job 1 (avg TMAX/TMIN per country-year).
Input : raw GHCN by_year CSV lines on stdin
Output: country|year \t tmax_sum,tmax_count,tmin_sum,tmin_count
Counters are reported through stderr using the streaming 'reporter:counter:' protocol.
"""
import sys


def counter(name):
    sys.stderr.write(f"reporter:counter:Quality,{name},1\n")


for line in sys.stdin:
    p = line.rstrip("\n").split(",")
    if len(p) < 7 or len(p[0]) != 11 or len(p[1]) != 8 or not p[3]:
        counter("MALFORMED")
        continue
    element = p[2]
    if element != "TMAX" and element != "TMIN":
        continue                      # not counted: avoids millions of stderr writes
    if p[5].strip():
        counter("QC_FAILED")
        continue
    try:
        v = int(p[3])
    except ValueError:
        counter("MALFORMED")
        continue
    if v == -9999:
        continue
    key = p[0][:2] + "|" + p[1][:4]
    if element == "TMAX":
        print(f"{key}\t{v},1,0,0")
    else:
        print(f"{key}\t0,0,{v},1")
