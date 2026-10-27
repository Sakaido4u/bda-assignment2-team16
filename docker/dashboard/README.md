# docker/dashboard

The dashboard image is built from `../../dashboard/Dockerfile`, so the Flask code and its Dockerfile stay together in one folder (`docker compose build dashboard`).

The same image (`bda16/dashboard:1.0`) also serves as the `tools` service. That service runs the Python scripts: MongoDB ingestion, profiling, summaries, dataset statistics and charts.

```powershell
docker compose run --rm tools python mongodb/ingest.py
```
