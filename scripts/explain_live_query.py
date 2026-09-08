"""Print a sanitized traditional EXPLAIN for the representative KPI query."""

import json
from pathlib import Path

import frappe


sql = Path("/tmp/ccd-dashboard-sql/ccd_person_service_presence.sql").read_text().strip().rstrip(";")
query = f"SELECT COUNT(DISTINCT logical_person_key) FROM ({sql}) p WHERE environment='Production'"
rows = frappe.db.sql("EXPLAIN " + query, as_dict=True)
for row in rows:
    row.pop("possible_keys", None)
    row.pop("key", None)
    print(json.dumps(row, default=str, sort_keys=True), flush=True)

