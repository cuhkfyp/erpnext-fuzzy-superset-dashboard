"""Read-only live metric reconciliation for execution inside a Frappe console.

Copy this repository's SQL files into ``/tmp/ccd-dashboard-sql`` in the backend
container, then run this file with ``exec(..., globals())``.  Output is aggregate
only and contains no client keys or row-level data.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe


SQL_DIR = Path("/tmp/ccd-dashboard-sql")


def _read(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text().strip().rstrip(";")


def _query(sql: str):
    return frappe.db.sql(sql, as_dict=True)


# Use explicit keyword names supported by both Python's stdlib and Frappe's
# console serializer without allowing row-level output.
def _print_result(result: dict[str, object]) -> None:
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


def run() -> dict[str, object]:
    person_sql = _read("ccd_person_service_presence")
    identity_sql = _read("ccd_identity_operations")
    quality_sql = _read("ccd_data_quality")
    dataset_counts = _query(
        "SELECT COALESCE(environment,'ALL') AS environment, "
        "COUNT(DISTINCT logical_person_key) AS logical_clients, "
        "SUM(source_row_count) AS source_rows, COUNT(DISTINCT source) AS populated_sources "
        f"FROM ({person_sql}) person_presence GROUP BY environment WITH ROLLUP"
    )
    direct_counts = _query(
        """
        WITH RECURSIVE registration_lineage AS (
            SELECT name AS current_registration, name AS source_name, amended_from, 0 AS depth
            FROM `tabCCD Registration` WHERE docstatus=1
            UNION ALL
            SELECT rl.current_registration, parent.name, parent.amended_from, rl.depth+1
            FROM registration_lineage rl JOIN `tabCCD Registration` parent
              ON parent.name=rl.amended_from WHERE rl.depth<100
        ), resolved AS (
            SELECT source_name,MAX(current_registration) AS current_registration
            FROM registration_lineage GROUP BY source_name
        ), included AS (
            SELECT rr.source_name,r.custom_dashboard_environment AS environment
            FROM resolved rr JOIN `tabCCD Registration` r ON r.name=rr.current_registration
            WHERE r.custom_include_in_dashboard=1
              AND r.custom_dashboard_environment IN ('Production','UAT','SIT','Development','Test')
        ), included_records AS (
            SELECT m.name,m.ccd_reg_source,i.environment
            FROM `tabCCD Master` m JOIN included i ON i.source_name=m.ccd_reg_source
        ), current_membership AS (
            SELECT im.ccd_master,MAX(im.identity_group) AS identity_group
            FROM `tabCCD Identity Membership` im JOIN `tabCCD Identity Group` ig
              ON ig.name=im.identity_group AND ig.status IN ('Active','Needs Revalidation')
            WHERE im.status='Active' AND (im.valid_to IS NULL OR im.valid_to>CURRENT_TIMESTAMP)
            GROUP BY im.ccd_master
        ), raw_counts AS (
            SELECT environment,COUNT(*) AS source_rows,COUNT(DISTINCT ccd_reg_source) AS populated_sources
            FROM included_records GROUP BY environment
        ), grouped_by_environment AS (
            SELECT ir.environment,cm.identity_group,COUNT(*) AS member_rows
            FROM included_records ir JOIN current_membership cm ON cm.ccd_master=ir.name
            GROUP BY ir.environment,cm.identity_group
        ), environment_reductions AS (
            SELECT environment,SUM(member_rows-1) AS reduction
            FROM grouped_by_environment GROUP BY environment
        ), all_reduction AS (
            SELECT COUNT(*)-COUNT(DISTINCT cm.identity_group) AS reduction
            FROM included_records ir JOIN current_membership cm ON cm.ccd_master=ir.name
        )
        SELECT rc.environment,rc.source_rows-COALESCE(er.reduction,0) AS logical_clients,
               rc.source_rows,rc.populated_sources
        FROM raw_counts rc LEFT JOIN environment_reductions er ON er.environment=rc.environment
        UNION ALL
        SELECT 'ALL',COUNT(*)-COALESCE((SELECT reduction FROM all_reduction),0),
               COUNT(*),COUNT(DISTINCT ccd_reg_source)
        FROM included_records
        """
    )
    identity_summary = _query(
        "SELECT operation_area,status,detail,metric_count,group_size "
        f"FROM ({identity_sql}) identity_ops WHERE operation_area IN "
        "('Governed Groups','Memberships','Group Size Distribution') "
        "ORDER BY operation_area,status,group_size"
    )
    quality_summary = _query(
        "SELECT source,classification,environment,source_row_count,sex_mapping_ready,"
        "placeholder_sex_rows,dob_mapping_ready,dob_key_mapping_ready,valid_district_rows,"
        "unmapped_location_rows,missing_district_rows,growth_readiness "
        f"FROM ({quality_sql}) data_quality ORDER BY classification,source"
    )
    result = {
        "dataset_by_environment": dataset_counts,
        "direct_by_environment": direct_counts,
        "identity_summary": identity_summary,
        "data_quality": quality_summary,
        "reconciled": {
            row["environment"]: (row["logical_clients"], row["source_rows"], row["populated_sources"])
            for row in dataset_counts
        } == {
            row["environment"]: (row["logical_clients"], row["source_rows"], row["populated_sources"])
            for row in direct_counts
        },
    }
    _print_result(result)
    if not result["reconciled"]:
        raise AssertionError("Virtual dataset totals do not match independent direct SQL")
    return result


run()
