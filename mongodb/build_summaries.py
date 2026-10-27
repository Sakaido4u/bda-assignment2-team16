#!/usr/bin/env python3
"""Materialise ghcn.summary_country_month with a MongoDB aggregation ($unwind/$group/$lookup/$merge).

The dashboard's Climate page reads this small collection (a few thousand documents) instead of
re-aggregating ~20 million station-day documents on every page load.

  docker compose run --rm tools python mongodb/build_summaries.py
"""
import os
import time

from pymongo import MongoClient

db = MongoClient(f"mongodb://{os.environ.get('MONGO_HOST', 'localhost')}:{os.environ.get('MONGO_PORT', '27017')}").ghcn

PIPELINE = [
    {"$unwind": "$readings"},
    {"$group": {
        "_id": {"c": "$country_code", "y": "$year", "m": "$month", "e": "$readings.element"},
        "avg": {"$avg": "$readings.value"},
        "sum": {"$sum": "$readings.value"},
        "min": {"$min": "$readings.value"},
        "max": {"$max": "$readings.value"},
        "n": {"$sum": 1},
        "over_40": {"$sum": {"$cond": [{"$gt": ["$readings.value", 40]}, 1, 0]}},
        "stations": {"$addToSet": "$station_id"},
    }},
    {"$lookup": {"from": "countries", "localField": "_id.c", "foreignField": "_id", "as": "country"}},
    {"$project": {
        "_id": {"$concat": ["$_id.c", "-", {"$toString": "$_id.y"}, "-", {"$toString": "$_id.m"}, "-", "$_id.e"]},
        "country_code": "$_id.c", "country_name": {"$first": "$country.name"},
        "year": "$_id.y", "month": "$_id.m", "element": "$_id.e",
        "avg": 1, "sum": 1, "min": 1, "max": 1, "n": 1,
        # over_40 is only meaningful for temperatures
        "over_40": {"$cond": [{"$in": ["$_id.e", ["TMAX", "TMIN"]]}, "$over_40", 0]},
        "n_stations": {"$size": "$stations"},
    }},
    {"$merge": {"into": "summary_country_month", "whenMatched": "replace", "whenNotMatched": "insert"}},
]

t0 = time.time()
db.summary_country_month.drop()
db.observations.aggregate(PIPELINE, allowDiskUse=True)
db.summary_country_month.create_index([("country_code", 1), ("year", 1), ("month", 1)])
print(f"summary_country_month: {db.summary_country_month.count_documents({}):,} documents "
      f"built in {time.time() - t0:.1f} s")
