// =====================================================================
//  Theme 1 - MongoDB indexing and aggregation pipelines (GHCN-Daily)
//  Run:  docker cp mongodb\queries.js mongodb:/tmp/queries.js
//        docker exec mongodb mongosh --quiet ghcn /tmp/queries.js
//  Stages used: $match $unwind $group $project $sort $limit $lookup $facet $bucket $geoNear $addFields
// =====================================================================
db = db.getSiblingDB("ghcn");
const BLR = { type: "Point", coordinates: [77.5946, 12.9716] };   // Bengaluru [lon, lat]
const STATION = "IN009010100";                                      // BANGALORE (GSN)
function show(title, cursor) {
  print("\n==== " + title + " ====");
  const t0 = Date.now();
  const rows = cursor.toArray();
  // one compact line per result document (nested $facet output is printed per facet)
  rows.forEach(r => {
    const keys = Object.keys(r);
    if (keys.every(k => Array.isArray(r[k]))) {
      keys.forEach(k => { print(`-- ${k}:`); r[k].forEach(x => print("   " + EJSON.stringify(x, { relaxed: true }))); });
    } else print(EJSON.stringify(r, { relaxed: true }));
  });
  print(`(${rows.length} documents, ${Date.now() - t0} ms)`);
}

// ---------------------------------------------------------------- indexes
print("==== Creating indexes ====");
db.observations.createIndex({ station_id: 1, date: 1 }, { name: "station_date" });
db.observations.createIndex({ "readings.element": 1 }, { name: "element" });
db.stations.createIndex({ location: "2dsphere" }, { name: "location_2dsphere" });
print("observations:"); printjson(db.observations.getIndexes());
print("stations:");     printjson(db.stations.getIndexes());
print("observations count: " + db.observations.estimatedDocumentCount() +
      "   stations count: " + db.stations.estimatedDocumentCount());

// ------------------------------------------- Q1 yearly average TMAX / TMIN per country
show("Q1 Yearly average TMAX/TMIN per country (top 15 by readings)", db.observations.aggregate([
  { $unwind: "$readings" },
  { $match: { "readings.element": { $in: ["TMAX", "TMIN"] } } },
  { $group: { _id: { c: "$country_code", y: "$year", e: "$readings.element" },
              avg: { $avg: "$readings.value" }, n: { $sum: 1 } } },
  { $group: { _id: { c: "$_id.c", y: "$_id.y" },
              avg_tmax: { $max: { $cond: [{ $eq: ["$_id.e", "TMAX"] }, "$avg", null] } },
              avg_tmin: { $max: { $cond: [{ $eq: ["$_id.e", "TMIN"] }, "$avg", null] } },
              readings: { $sum: "$n" } } },
  { $lookup: { from: "countries", localField: "_id.c", foreignField: "_id", as: "country" } },
  { $project: { _id: 0, country_code: "$_id.c", country: { $first: "$country.name" }, year: "$_id.y",
                avg_tmax: { $round: ["$avg_tmax", 2] }, avg_tmin: { $round: ["$avg_tmin", 2] }, readings: 1 } },
  { $sort: { readings: -1, year: 1 } },
  { $limit: 15 }
], { allowDiskUse: true }));

// ------------------------------------------- Q2 top 10 hottest and wettest stations in India
show("Q2 Top 10 hottest (avg TMAX) and wettest (total PRCP) stations in India", db.observations.aggregate([
  { $match: { station_id: { $regex: "^IN" } } },          // anchored prefix -> uses station_date index
  { $unwind: "$readings" },
  { $facet: {
      hottest: [
        { $match: { "readings.element": "TMAX" } },
        { $group: { _id: "$station_id", avg_tmax: { $avg: "$readings.value" }, days: { $sum: 1 } } },
        { $match: { days: { $gte: 300 } } },
        { $sort: { avg_tmax: -1 } }, { $limit: 10 },
        { $lookup: { from: "stations", localField: "_id", foreignField: "_id", as: "s" } },
        { $project: { _id: 0, station_id: "$_id", name: { $first: "$s.name" },
                      avg_tmax: { $round: ["$avg_tmax", 2] }, days: 1 } } ],
      wettest: [
        { $match: { "readings.element": "PRCP" } },
        { $group: { _id: "$station_id", total_mm: { $sum: "$readings.value" }, days: { $sum: 1 } } },
        { $sort: { total_mm: -1 } }, { $limit: 10 },
        { $lookup: { from: "stations", localField: "_id", foreignField: "_id", as: "s" } },
        { $project: { _id: 0, station_id: "$_id", name: { $first: "$s.name" },
                      total_mm: { $round: ["$total_mm", 1] }, days: 1 } } ]
  } }
]));

// ------------------------------------------- Q3 monthly precipitation totals for one station
show("Q3 Monthly precipitation totals - " + STATION + " (Bangalore)", db.observations.aggregate([
  { $match: { station_id: STATION } },
  { $unwind: "$readings" },
  { $match: { "readings.element": "PRCP" } },
  { $group: { _id: { y: "$year", m: "$month" }, total_mm: { $sum: "$readings.value" },
              reported_days: { $sum: 1 },
              rain_days: { $sum: { $cond: [{ $gte: ["$readings.value", 2.5] }, 1, 0] } } } },
  { $project: { _id: 0, year: "$_id.y", month: "$_id.m", total_mm: { $round: ["$total_mm", 1] },
                rain_days: 1, reported_days: 1 } },
  { $sort: { year: 1, month: 1 } }
]));

// ------------------------------------------- Q4 extreme-heat days (TMAX > 40 C) per year
show("Q4 Extreme-heat station-days (TMAX > 40 C) per year", db.observations.aggregate([
  { $match: { readings: { $elemMatch: { element: "TMAX", value: { $gt: 40 } } } } },
  { $unwind: "$readings" },
  { $match: { "readings.element": "TMAX", "readings.value": { $gt: 40 } } },
  { $group: { _id: "$year", heat_days: { $sum: 1 }, stations: { $addToSet: "$station_id" },
              countries: { $addToSet: "$country_code" }, max_tmax: { $max: "$readings.value" } } },
  { $project: { _id: 0, year: "$_id", heat_days: 1, max_tmax: 1,
                n_stations: { $size: "$stations" }, n_countries: { $size: "$countries" } } },
  { $sort: { year: 1 } }
]));

// ------------------------------------------- Q5 one $facet call: temperature, precipitation, stations
show("Q5 $facet - temperature stats, precipitation stats, station counts, TMAX histogram", db.observations.aggregate([
  { $facet: {
      temperature: [
        { $unwind: "$readings" },
        { $match: { "readings.element": { $in: ["TMAX", "TMIN"] } } },
        { $group: { _id: "$readings.element", avg: { $avg: "$readings.value" },
                    min: { $min: "$readings.value" }, max: { $max: "$readings.value" }, n: { $sum: 1 } } },
        { $project: { avg: { $round: ["$avg", 2] }, min: 1, max: 1, n: 1 } } ],
      precipitation: [
        { $unwind: "$readings" },
        { $match: { "readings.element": "PRCP" } },
        { $group: { _id: null, total_mm: { $sum: "$readings.value" }, avg_mm: { $avg: "$readings.value" },
                    max_mm: { $max: "$readings.value" }, n: { $sum: 1 },
                    wet_days: { $sum: { $cond: [{ $gte: ["$readings.value", 1] }, 1, 0] } } } },
        { $project: { _id: 0, avg_mm: { $round: ["$avg_mm", 2] }, max_mm: 1, n: 1, wet_days: 1 } } ],
      stations_per_country: [
        { $group: { _id: "$station_id", c: { $first: "$country_code" } } },
        { $group: { _id: "$c", stations: { $sum: 1 } } },
        { $sort: { stations: -1 } }, { $limit: 10 } ],
      tmax_histogram: [
        { $unwind: "$readings" },
        { $match: { "readings.element": "TMAX" } },
        { $bucket: { groupBy: "$readings.value", boundaries: [-70, -20, -10, 0, 10, 20, 30, 40, 50, 70],
                     default: "out_of_range", output: { n: { $sum: 1 } } } } ]
  } }
], { allowDiskUse: true }));

// ------------------------------------------- Q6 geospatial: stations within 200 km of Bengaluru
show("Q6 Stations within 200 km of Bengaluru ($geoNear, 2dsphere index)", db.stations.aggregate([
  { $geoNear: { near: BLR, distanceField: "dist_m", maxDistance: 200000, spherical: true } },
  { $project: { _id: 0, station_id: 1, name: 1, elevation: 1, dist_km: { $round: [{ $divide: ["$dist_m", 1000] }, 1] } } },
  { $limit: 25 }
]));

// ------------------------------------------- Q7 geo + $lookup: climate of the stations near Bengaluru
show("Q7 Average TMAX/TMIN and total rain of stations within 200 km of Bengaluru", db.stations.aggregate([
  { $geoNear: { near: BLR, distanceField: "dist_m", maxDistance: 200000, spherical: true } },
  { $lookup: { from: "observations", localField: "station_id", foreignField: "station_id",
               pipeline: [ { $unwind: "$readings" },
                           { $group: { _id: "$readings.element", avg: { $avg: "$readings.value" },
                                       sum: { $sum: "$readings.value" }, n: { $sum: 1 } } } ],
               as: "obs" } },
  { $match: { "obs.0": { $exists: true } } },
  { $project: { _id: 0, station_id: 1, name: 1, dist_km: { $round: [{ $divide: ["$dist_m", 1000] }, 1] },
                obs: { $map: { input: "$obs", as: "o",
                               in: { element: "$$o._id", avg: { $round: ["$$o.avg", 2] }, n: "$$o.n" } } } } }
]));

// ------------------------------------------- explain() example (winning plan)
print("\n==== explain(executionStats) for Q3's $match ====");
const ex = db.observations.find({ station_id: STATION }).explain("executionStats");
printjson({ winningStage: ex.queryPlanner.winningPlan.inputStage ? ex.queryPlanner.winningPlan.inputStage.stage : ex.queryPlanner.winningPlan.stage,
            executionTimeMillis: ex.executionStats.executionTimeMillis,
            totalKeysExamined: ex.executionStats.totalKeysExamined,
            totalDocsExamined: ex.executionStats.totalDocsExamined,
            nReturned: ex.executionStats.nReturned });
