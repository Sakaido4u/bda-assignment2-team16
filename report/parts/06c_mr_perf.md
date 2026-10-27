### 6.3 MapReduce – Java vs Python Streaming

Both versions of Job 1 read the same 4.07 GB with the same 122 map tasks, 2 reducers and a combiner on the same 2 workers, and they produced the same 560 output rows:

| Measure | Java | Python Streaming | Difference |
|---|---|---|---|
| Wall-clock time | **208.9 s** | **290.6 s** | Streaming +39 % |
| JobHistory elapsed (submit → finish) | 197.6 s | 279.1 s | +41 % |
| Map output records | 26,197,386 | 26,197,386 | identical |
| Records after combiner | 20,762 | 20,762 | identical |
| Reduce shuffle bytes | 873,468 | 555,956 | Streaming smaller: plain-text values vs a 32-byte Writable |
| Job 2 (Java only) | 190.4 s | – | lighter mapper output (200 k records) |

![Fig. R6: Java vs Python Streaming](../results/charts/mapreduce_times.png)

**Why Streaming is slower.**
1. Every record crosses a **process boundary twice**: the Java map task writes the line to the Python process's stdin, and Python writes its output back to stdout, where Java parses it again.
2. CPython parses each line with an interpreted `split(',')` and builds Python objects, while the Java mapper reuses `Text`/`Writable` objects without allocating.
3. Every task also pays the start-up cost of a Python interpreter on top of the JVM.

The shuffle itself is not the bottleneck: the combiner shrinks it to well under 1 MB in both cases. The difference is pure map-side CPU.

**When Streaming is still the right choice.** It needed about 60 lines of Python instead of five Java classes plus a Maven build, and it can reuse any Python library. For exploratory jobs, or ones that are I/O-bound rather than CPU-bound, the 40 % penalty is often acceptable. For production jobs that run repeatedly over large inputs, Java (or Hive/Pig, which compile to Java) is preferable.

**Effect of the Combiner.** Without it, Job 1 would shuffle 26.2 M records (several hundred MB) to two reducers. With it, only 20,762 records are shuffled, about 1/1,262 of the volume, and both reduce tasks finish in a couple of seconds. The Combiner is the single most important optimisation in this job, and it is only correct because the custom `TempStatsWritable` carries sums and counts rather than averages.
