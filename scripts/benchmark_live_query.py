"""Time representative live chart queries from a Frappe console."""

import time
from pathlib import Path

import frappe


sql = Path("/tmp/ccd-dashboard-sql/ccd_person_service_presence.sql").read_text().strip().rstrip(";")
sql = sql.replace(
    "/*__HK_DISTRICT_GEOMETRY_ROWS__*/",
    "SELECT NULL AS district_code, NULL AS district_polygon WHERE 0",
)
queries = [
    (
        "production_logical",
        f"SELECT COUNT(DISTINCT logical_person_key) FROM ({sql}) p WHERE environment='Production'",
    ),
    (
        "production_age",
        f"SELECT age_band,dob_confidence,COUNT(DISTINCT logical_person_key) "
        f"FROM ({sql}) p WHERE environment='Production' GROUP BY age_band,dob_confidence",
    ),
    (
        "production_growth",
        f"SELECT overall_growth_month,COUNT(DISTINCT logical_person_key) "
        f"FROM ({sql}) p WHERE environment='Production' "
        f"AND overall_growth_month IS NOT NULL GROUP BY overall_growth_month",
    ),
]
for label, query in queries:
    started = time.monotonic()
    result = frappe.db.sql(query)
    print(
        label,
        "seconds=",
        round(time.monotonic() - started, 3),
        "rows=",
        len(result),
        "first=",
        result[0] if result else None,
        flush=True,
    )
