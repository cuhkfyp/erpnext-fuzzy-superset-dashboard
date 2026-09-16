"""Validate growth, local district inference, and map data in a Frappe console.

Copy ``sql/`` to ``/tmp/ccd-dashboard-sql`` and the simplified GeoJSON to
``/tmp/ccd-dashboard-assets/hk_districts_simplified.geojson`` before running.
Only aggregate results are printed; client keys and address text never leave
MariaDB.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import frappe


SQL_DIR = Path("/tmp/ccd-dashboard-sql")
GEOMETRY_PATH = Path("/tmp/ccd-dashboard-assets/hk_districts_simplified.geojson")
GEOMETRY_MARKER = "/*__HK_DISTRICT_GEOMETRY_ROWS__*/"


def geometry_rows() -> str:
    payload = json.loads(GEOMETRY_PATH.read_text())
    rows = []
    for feature in payload["features"]:
        code = feature["properties"]["district_code"]
        coordinates = json.dumps(feature["geometry"]["coordinates"], separators=(",", ":"))
        rows.append(f"SELECT '{code}' AS district_code, '{coordinates}' AS district_polygon")
    if len(rows) != 18:
        raise RuntimeError("Expected 18 Hong Kong district geometries")
    return "\nUNION ALL\n".join(rows)


def read_sql(name: str) -> str:
    sql = (SQL_DIR / f"{name}.sql").read_text().strip().rstrip(";")
    if GEOMETRY_MARKER in sql:
        sql = sql.replace(GEOMETRY_MARKER, geometry_rows())
    return sql


def timed(label: str, query: str):
    started = time.monotonic()
    rows = frappe.db.sql(query, as_dict=True)
    return {
        "label": label,
        "seconds": round(time.monotonic() - started, 3),
        "rows": rows,
    }


person_sql = read_sql("ccd_person_service_presence")
map_sql = read_sql("ccd_district_map")
quality_sql = read_sql("ccd_data_quality")
overlap_sql = read_sql("ccd_service_overlap")
identity_sql = read_sql("ccd_identity_operations")

results = [
    timed(
        "growth_by_environment",
        "SELECT environment, COUNT(DISTINCT logical_person_key) AS logical_clients, "
        "COUNT(DISTINCT CASE WHEN overall_growth_month IS NOT NULL THEN logical_person_key END) "
        "AS clients_with_growth_date, MIN(overall_growth_month) AS earliest_month, "
        "MAX(overall_growth_month) AS latest_month "
        f"FROM ({person_sql}) p GROUP BY environment ORDER BY environment",
    ),
    timed(
        "map_by_environment_and_basis",
        "SELECT environment, district_basis, COUNT(DISTINCT logical_person_key) AS clients, "
        "COUNT(DISTINCT district_code) AS districts "
        f"FROM ({map_sql}) m GROUP BY environment, district_basis "
        "ORDER BY environment, district_basis",
    ),
    timed(
        "development_sex_by_source",
        "SELECT source, sex_category, COUNT(DISTINCT logical_person_key) AS clients "
        f"FROM ({person_sql}) p WHERE environment='Development' "
        "GROUP BY source, sex_category ORDER BY source, sex_category",
    ),
    timed(
        "production_multi_service_clients",
        "SELECT COUNT(DISTINCT logical_person_key) AS clients "
        f"FROM ({person_sql}) p WHERE environment='Production' AND services_per_person > 1",
    ),
    timed(
        "interconnectivity_by_environment",
        "SELECT environment, endpoint_a, endpoint_b, "
        "COUNT(DISTINCT logical_person_key) AS clients "
        f"FROM ({overlap_sql}) o GROUP BY environment, endpoint_a, endpoint_b "
        "ORDER BY environment, endpoint_a, endpoint_b",
    ),
    timed(
        "global_group_source_interconnectivity",
        "SELECT status AS endpoint_a, detail AS endpoint_b, metric_count AS groups "
        f"FROM ({identity_sql}) i WHERE operation_area='Group Source Composition' "
        "ORDER BY status, detail",
    ),
    timed(
        "location_quality",
        "SELECT source, environment, valid_district_rows, inferred_district_rows, "
        "ambiguous_address_rows, unmapped_location_rows, missing_district_rows "
        f"FROM ({quality_sql}) q WHERE classification='Included' ORDER BY environment, source",
    ),
]
print(json.dumps(results, ensure_ascii=False, default=str, indent=2), flush=True)
