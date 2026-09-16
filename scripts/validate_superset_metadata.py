#!/usr/bin/env python3
"""Read-only audit of the installed governed CCD Superset metadata."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


DASHBOARD_SLUG = "common-client-database-governed"
DATASETS = {
    "ccd_person_service_presence",
    "ccd_district_map",
    "ccd_service_overlap",
    "ccd_identity_operations",
    "ccd_data_quality",
}
FORBIDDEN_COLUMNS = {
    "name",
    "client_name",
    "first_name",
    "last_name",
    "mobile",
    "phone",
    "email",
    "address",
    "address_line_1",
    "address_line_2",
    "hkid",
    "identity_number",
}
FORBIDDEN_PERMISSION_FRAGMENTS = (
    "sql lab",
    "sqllab",
    "database_access",
    "schema_access",
    "all_datasource_access",
    "csv",
    "export",
    "drill",
)


def connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def validate(args: argparse.Namespace) -> dict[str, object]:
    conn = connect(args.metadata_db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        dashboard = conn.execute(
            "SELECT id,json_metadata FROM dashboards WHERE slug=?", (DASHBOARD_SLUG,)
        ).fetchone()
        assert dashboard and dashboard[0] != 5
        dashboard_id, metadata_text = dashboard
        assert conn.execute(
            "SELECT COUNT(*) FROM dashboard_slices WHERE dashboard_id=?", (dashboard_id,)
        ).fetchone()[0] == 26

        owner = conn.execute(
            """SELECT u.username FROM dashboard_user du
               JOIN ab_user u ON u.id=du.user_id WHERE du.dashboard_id=?""",
            (dashboard_id,),
        ).fetchall()
        assert owner == [("gest-ai",)]

        rows = conn.execute(
            "SELECT id,table_name,cache_timeout,is_sqllab_view FROM tables "
            f"WHERE table_name IN ({','.join('?' for _ in DATASETS)})",
            tuple(sorted(DATASETS)),
        ).fetchall()
        assert {row[1] for row in rows} == DATASETS
        dataset_ids = {row[0] for row in rows}
        assert all(row[2] == 0 and row[3] == 0 for row in rows)
        columns = {
            row[0]
            for row in conn.execute(
                f"SELECT lower(column_name) FROM table_columns WHERE table_id IN ({','.join('?' for _ in dataset_ids)})",
                tuple(dataset_ids),
            )
        }
        assert not (columns & FORBIDDEN_COLUMNS)

        role = conn.execute("SELECT id FROM ab_role WHERE name='CCD Dashboard Viewer'").fetchone()
        assert role
        role_id = role[0]
        assert conn.execute(
            "SELECT COUNT(*) FROM dashboard_roles WHERE dashboard_id=? AND role_id=?",
            (dashboard_id, role_id),
        ).fetchone()[0] == 1
        permissions = conn.execute(
            """SELECT p.name,v.name FROM ab_permission_view_role pvr
               JOIN ab_permission_view pv ON pv.id=pvr.permission_view_id
               JOIN ab_permission p ON p.id=pv.permission_id
               JOIN ab_view_menu v ON v.id=pv.view_menu_id
               WHERE pvr.role_id=?""",
            (role_id,),
        ).fetchall()
        assert not any(
            fragment in f"{permission} {view}".lower()
            for permission, view in permissions
            for fragment in FORBIDDEN_PERMISSION_FRAGMENTS
        )
        datasource_views = {
            view for permission, view in permissions if permission == "datasource_access"
        }
        assert len(datasource_views) == 5
        assert all(any(f"[{name}]" in view for name in DATASETS) for view in datasource_views)
        assert not any("(id:48)" in view for view in datasource_views)

        metadata = json.loads(metadata_text)
        assert metadata["refresh_frequency"] == 0
        assert metadata["cross_filters_enabled"] is False
        filters = metadata["native_filter_configuration"]
        assert [item["name"] for item in filters] == [
            "Environment / 環境",
            "Service / 服務",
            "Source / 來源",
        ]
        assert filters[0]["defaultDataMask"]["filterState"]["value"] == ["Production"]
        assert filters[1]["cascadeParentIds"] == [filters[0]["id"]]
        assert filters[2]["cascadeParentIds"] == [filters[0]["id"], filters[1]["id"]]
        global_charts = set(metadata["ccd_global_identity_charts"])
        assert len(global_charts) == 7
        assert all(global_charts.isdisjoint(set(item["chartsInScope"])) for item in filters)

        roles = {
            row[0]
            for row in conn.execute(
                """SELECT r.name FROM ab_user u JOIN ab_user_role ur ON ur.user_id=u.id
                   JOIN ab_role r ON r.id=ur.role_id WHERE u.username='gest-ai'"""
            )
        }
        assert "Alpha" in roles
        if args.require_finalized:
            assert "Admin" not in roles

        if args.dashboard5_baseline:
            baseline_conn = connect(args.dashboard5_baseline)
            try:
                protected_sql = (
                    "SELECT dashboard_title,slug,position_json,json_metadata FROM dashboards WHERE id=5"
                )
                assert conn.execute(protected_sql).fetchone() == baseline_conn.execute(protected_sql).fetchone()
            finally:
                baseline_conn.close()

        result = {
            "dashboard_id": dashboard_id,
            "dashboard_5_unchanged": bool(args.dashboard5_baseline),
            "dataset_ids": sorted(dataset_ids),
            "chart_count": 26,
            "viewer_permission_count": len(permissions),
            "viewer_dataset_permissions": len(datasource_views),
            "gest_ai_roles": sorted(roles),
            "identity_charts_global": len(global_charts),
            "integrity_check": "ok",
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-db", type=Path, required=True)
    parser.add_argument("--dashboard5-baseline", type=Path)
    parser.add_argument("--require-finalized", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    validate(parse_args())
