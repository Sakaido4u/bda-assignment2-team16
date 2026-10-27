#!/usr/bin/env python3
"""Assembles report/report.md from report/parts/*.md and generates the screenshot appendix and
report/screenshot-checklist.md from one caption list, so figure numbers always match the files.

  python report/tools/build_report.py      (run from the project root)
"""
import os

R = "report"

# (file stem, caption, how to reproduce)
SHOTS = [
    ("A", "Cluster and environment", [
        ("fig01_compose_ps", "docker compose ps – master, worker1, worker2, metastore-db, mongodb, dashboard running", "docker compose ps"),
        ("fig02_dfsadmin_report", "hdfs dfsadmin -report – 2 live DataNodes (worker1, worker2), 0 under-replicated blocks", ".\\scripts\\cluster-status.ps1"),
        ("fig03_yarn_nodes_jps", "yarn node -list -all (2 RUNNING NodeManagers) and jps on every node", ".\\scripts\\cluster-status.ps1"),
        ("fig04_config_versions", "Effective configuration (replication 2, 32 MB blocks, YARN memory), workers file, versions", "hdfs getconf -confKey …"),
        ("fig05_namenode_overview", "NameNode web UI – overview, 2 live nodes, capacity", "http://localhost:9870"),
        ("fig06_namenode_datanodes", "NameNode UI – Datanodes tab: worker1 and worker2 In Service with similar block counts", "http://localhost:9870/dfshealth.html#tab-datanode"),
        ("fig07_datanode_worker1", "DataNode UI of worker1", "http://localhost:9864"),
        ("fig08_datanode_worker2", "DataNode UI of worker2", "http://localhost:9865"),
        ("fig09_rm_cluster", "ResourceManager UI – cluster metrics (3 GB, 6 vcores, 2 active nodes)", "http://localhost:8088/cluster"),
        ("fig10_rm_nodes", "ResourceManager UI – Nodes: worker1 and worker2 RUNNING", "http://localhost:8088/cluster/nodes"),
        ("fig11_nm_worker1", "NodeManager UI of worker1", "http://localhost:8042"),
        ("fig12_nm_worker2", "NodeManager UI of worker2", "http://localhost:8043"),
        ("fig13_hs2_ui", "HiveServer2 web UI", "http://localhost:10002"),
    ]),
    ("A", "Theme 2 – HDFS", [
        ("fig14_hdfs_mkdir_put", "hdfs dfs -mkdir -p and -put (raw yearly files streamed from gzip, stations, countries)", "scripts/hdfs-operations.sh"),
        ("fig15_hdfs_ls_du", "hdfs dfs -ls -R and -du -h (logical size and size with 2 replicas)", "scripts/hdfs-operations.sh"),
        ("fig16_hdfs_cat_get_rm", "hdfs dfs -cat | head, -get, -cp, -rm -r", "scripts/hdfs-operations.sh"),
        ("fig17_hdfs_stat_fsck", "hdfs dfs -stat (replication=2, blocksize=33554432) and fsck -files -blocks -locations", "scripts/hdfs-operations.sh"),
        ("fig18_hdfs_fsck_summary", "fsck summary (HEALTHY, avg replication 2.0) and replicas per DataNode: 126 on each worker", "scripts/hdfs-operations.sh"),
        ("fig19_namenode_browse", "NameNode file browser – /ghcn/raw", "Utilities → Browse the file system"),
        ("fig20_namenode_block_locations", "File information for 2025.csv – Block 0 available on worker1 and worker2", "click 2025.csv in the browser"),
    ]),
    ("A", "Theme 2 – MapReduce", [
        ("fig21_mr_build", "Maven build inside a container and the classes in ghcn-mapreduce.jar", "mapreduce\\build.ps1"),
        ("fig22_mr_job1_java", "Job 1 (Java) on YARN – 122 data-local maps, combiner output 20,762, custom counters", "mapreduce/run-jobs.sh"),
        ("fig23_mr_job2_java", "Job 2 (Java) – extreme-precipitation days, EXTREME_DAYS / QC_FAILED counters", "mapreduce/run-jobs.sh"),
        ("fig24_mr_job1_streaming", "Job 1 with Python Streaming (mapper/combiner/reducer)", "mapreduce/run-jobs.sh"),
        ("fig25_mr_outputs", "Outputs: India yearly averages, top extreme-rain stations, Java vs Streaming equivalence check", "mapreduce/run-jobs.sh"),
        ("fig26_mr_hdfs_output", "MapReduce output files in HDFS (part-r-00000, part-r-00001)", "hdfs dfs -cat /ghcn/output/…"),
        ("fig27_mr_task_nodes", "Tasks per worker for each job (JobHistory REST API) and timing table", "mapreduce/task_nodes.py"),
        ("fig28_rm_apps", "ResourceManager UI – finished applications", "http://localhost:8088/cluster/apps"),
        ("fig29_jobhistory_jobs", "JobHistory UI – job list", "http://localhost:19888"),
        ("fig30_jobhistory_job1", "JobHistory – Job 1 overview (maps/reduces, elapsed, AM node)", "JobHistory → job"),
        ("fig31_jobhistory_job1_attempts_nodes", "JobHistory – successful map attempts with the Node column (worker1 / worker2)", "Map tasks → Successful"),
        ("fig32_jobhistory_job1_counters", "JobHistory – Job 1 counters including the custom Quality counters", "Counters"),
        ("fig33_jobhistory_job2", "JobHistory – Job 2 overview", "JobHistory → job"),
        ("fig34_jobhistory_streaming", "JobHistory – Streaming job overview", "JobHistory → job"),
        ("fig35_jobhistory_job2_reduce_nodes", "JobHistory – reduce attempts and their nodes", "Reduce tasks → Successful"),
        ("fig36_rm_nodes_running_containers", "ResourceManager Nodes page while the Pig job runs – containers on both workers", "during a job"),
        ("fig37_rm_pig_app_running", "ResourceManager – running Pig application", "during a job"),
    ]),
    ("A", "Theme 3 – Pig", [
        ("fig38_pig_describe_dump", "Pig DESCRIBE and DUMP on the 5,000-row sample (QC-failed rows, cleaned Indian rows, before/after counts)", "pig/run-pig.sh"),
        ("fig39_pig_illustrate", "Pig ILLUSTRATE – sample rows through raw → core → valid → clean", "pig/run-pig.sh"),
        ("fig40_pig_clean_job", "Full Pig cleaning job: 113,135,524 read → 86,871,554 stored", "pig/run-pig.sh"),
        ("fig41_pig_counts", "Record counts per cleaning stage, sizes and a sample of /ghcn/clean", "pig/run-pig.sh"),
        ("fig42_jobhistory_pig_job", "JobHistory – Pig, Hive and MapReduce jobs", "http://localhost:19888"),
    ]),
    ("A", "Theme 3 – Hive", [
        ("fig43_hive_create_tables", "beeline – external TEXTFILE table, RCFile table, INSERT OVERWRITE, equal row counts", "hive/01_create_tables.hql"),
        ("fig44_hive_bonus_tables", "BONUS – Snappy RCFile, ORC and monthly_summary tables", "hive/02_bonus_tables.hql"),
        ("fig45_hive_describe_rc", "SHOW TABLES and DESCRIBE FORMATTED obs_rc (RCFileInputFormat, LazyBinaryColumnarSerDe)", "beeline"),
        ("fig46_hive_benchmark_runs", "benchmark_hive.sh – every query × 3 runs per table", "hive/benchmark_hive.sh"),
        ("fig47_hive_benchmark_summary", "Benchmark summary (time, HDFS MB read, speed-up) and table sizes", "results/hive_benchmark_summary.csv"),
        ("fig48_hive_query_results", "Results of the benchmark queries", "results/logs/hive_query_results.log"),
        ("fig49_hs2_ui_queries", "HiveServer2 UI – the last 25 closed benchmark queries with latency", "http://localhost:10002"),
        ("fig50b_hdfs_warehouse", "Hive warehouse directory in HDFS (obs_rc, obs_rc_snappy, obs_orc, monthly_summary)", "NameNode file browser"),
    ]),
    ("A", "Theme 1 – MongoDB", [
        ("fig50_mongo_ingest", "Ingestion with pymongo insert_many – 20,386,429 documents, 34,454 docs/s", "mongodb/ingest.py"),
        ("fig51_mongo_sample_doc", "One station-day document with embedded readings; collection statistics", "mongosh"),
        ("fig52_mongoimport", "mongoimport alternative – 133,039 station documents", "mongodb/mongoimport_demo.ps1"),
        ("fig53_mongo_indexes", "createIndex and getIndexes() – compound, multikey and 2dsphere indexes", "mongodb/queries.js"),
        ("fig54_mongo_q1", "Q1 – yearly average TMAX/TMIN per country ($unwind, $group, $lookup, $project)", "mongodb/queries.js"),
        ("fig55_mongo_q2", "Q2 – hottest and wettest Indian stations ($facet, $lookup)", "mongodb/queries.js"),
        ("fig56_mongo_q3", "Q3 – monthly precipitation totals, Bangalore", "mongodb/queries.js"),
        ("fig57_mongo_q4_q7", "Q4 – extreme-heat station-days (TMAX > 40 °C) per year", "mongodb/queries.js"),
        ("fig58_mongo_q5", "Q5 – one $facet call: temperature, precipitation, stations per country, $bucket histogram", "mongodb/queries.js"),
        ("fig59_mongo_q6", "Q6 – $geoNear: stations within 200 km of Bengaluru", "mongodb/queries.js"),
        ("fig59b_mongo_q7_explain", "Q7 – $geoNear + $lookup climate of nearby stations; explain() of Q3 (IXSCAN)", "mongodb/queries.js"),
        ("fig60_mongo_profile", "explain(\"executionStats\") before vs after indexing – COLLSCAN → IXSCAN", "mongodb/profile_queries.py"),
    ]),
    ("B", "Part 2 – Flask dashboard", [
        ("figB1_dashboard_cluster_running", "Cluster page during the Pig job – all three nodes RUNNING, 3 containers on each worker", "http://localhost:5000/"),
        ("figB1b_dashboard_cluster_idle", "Cluster page with the cluster idle – recent applications", "http://localhost:5000/"),
        ("figB2_dashboard_climate_india", "Climate analytics – India", "http://localhost:5000/climate?country=IN"),
        ("figB3_dashboard_climate_australia", "Climate analytics – country selector (Australia)", "http://localhost:5000/climate?country=AS"),
        ("figB4_dashboard_map_bengaluru", "Station map – $geoNear 200 km around Bengaluru, station summary", "http://localhost:5000/map"),
        ("figB5_dashboard_hive_monthly", "Hive page – monthly averages India TMAX 2025 (monthly_summary)", "http://localhost:5000/hive"),
        ("figB6_dashboard_hive_hottest", "Hive page – hottest Indian stations 2024 (full scan of obs_rc + join on YARN)", "http://localhost:5000/hive"),
        ("figB7_dashboard_service_down", "Error handling – MongoDB stopped: readable error banner instead of a crash", "docker stop mongodb"),
        ("figB8_dashboard_performance", "Performance page – MongoDB index profiling, Hive formats, MapReduce", "http://localhost:5000/performance"),
    ]),
]


def label(prefix, stem):
    n = stem[3:].split("_")[0]
    if n[:2].isdigit():
        n = str(int(n[:2])) + n[2:]          # fig07 -> A7, fig50b -> A50b
    return f"Fig. {prefix}{n}" if prefix == "A" else f"Fig. {n}"


def main():
    appendix = ["### Appendix A – Part 1 screenshots", ""]
    check = ["# Screenshot checklist (all captured automatically into report/screenshots/)", "",
             "Every figure below exists as a PNG. Retake one by re-running the command in the last column; "
             "web pages were captured with `report/tools/capture.py` (Playwright, headless Chromium on the cluster network).", "",
             "| # | Figure | Caption | File | How to reproduce |", "|---|---|---|---|---|"]
    i = 0
    for prefix, group, shots in SHOTS:
        if prefix == "B" and "### Appendix B" not in "\n".join(appendix):
            appendix += ["### Appendix B – Part 2 (dashboard) screenshots", ""]
        appendix += [f"#### {group}", ""]
        for stem, cap, how in shots:
            path = f"{R}/screenshots/{stem}.png"
            assert os.path.exists(path), path
            i += 1
            lab = label(prefix, stem)
            appendix += [f"**{lab}: {cap}**", "", f"![{lab}](screenshots/{stem}.png)", ""]
            check.append(f"| {i} | {lab} | {cap} | `screenshots/{stem}.png` | `{how}` |")
    check += ["", "Report charts (generated by `scripts/make_charts.py` into `results/charts/`): dataset_elements, "
              "mr_hottest_countries, mr_task_nodes, mapreduce_times, pig_clean_funnel, mongo_profile_time, mongo_profile_docs, "
              "hive_query_time, hive_hdfs_read, hive_storage. Architecture diagrams: `report/diagrams/*.png` (Mermaid sources `*.mmd`)."]
    with open(f"{R}/screenshot-checklist.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(check) + "\n")

    order = ["00_head.md", "04_extension.md", "05a_theme1.md", "05b_theme2.md", "05c_pig.md", "05d_hive.md",
             "06_perf.md", "06c_mr_perf.md", "07_conclusion.md", "08_references.md", "09a_code.md"]
    parts = [open(f"{R}/parts/{p}", encoding="utf-8").read().rstrip() for p in order]
    body = "\n\n---\n\n".join(parts[:9]) + "\n\n---\n\n" + parts[9] + "\n\n---\n\n" + parts[10]
    body += "\n\n" + "\n".join(appendix) + "\n"
    with open(f"{R}/report.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    print(f"report.md: {len(body.split()):,} words, {i} screenshots in appendix; screenshot-checklist.md written")


if __name__ == "__main__":
    main()
