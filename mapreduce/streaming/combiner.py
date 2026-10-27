#!/usr/bin/env python3
"""Hadoop Streaming combiner: merges partial sums/counts (input and output have the same format)."""
import sys

cur, acc = None, [0, 0, 0, 0]
for line in sys.stdin:
    key, val = line.rstrip("\n").split("\t", 1)
    nums = [int(x) for x in val.split(",")]
    if key != cur:
        if cur is not None:
            print(f"{cur}\t{acc[0]},{acc[1]},{acc[2]},{acc[3]}")
        cur, acc = key, [0, 0, 0, 0]
    for i in range(4):
        acc[i] += nums[i]
if cur is not None:
    print(f"{cur}\t{acc[0]},{acc[1]},{acc[2]},{acc[3]}")
