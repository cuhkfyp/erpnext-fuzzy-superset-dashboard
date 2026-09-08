#!/usr/bin/env python3
"""Install the governed CCD virtual datasets, charts, dashboard, and viewer role.

This installer intentionally operates only on Superset's metadata SQLite file.
It is idempotent, uses stable UUIDs, never reads database credentials, and never
updates dashboard id 5.  Run it first against a disposable metadata copy.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = uuid.UUID("7e039277-2227-4bbc-82c2-6be8af84ab52")
DASHBOARD_SLUG = "common-client-database-governed"
DASHBOARD_TITLE = "Common Client Database / 共同客戶資料庫"
VIEWER_ROLE = "CCD Dashboard Viewer"


def stable_uuid(kind: str, key: str) -> bytes:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}").bytes


def now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(" ")


def next_id(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COALESCE(MAX(id), 0) + 1 FROM "{table}"').fetchone()[0]


def load_json(name: str) -> Any:
    return json.loads((ROOT / "manifests" / name).read_text())


def sql_metric(expression: str) -> dict[str, Any]:
    return {
        "expressionType": "SQL",
        "sqlExpression": expression,
        "column": None,
        "aggregate": None,
        "datasourceWarning": False,
        "hasCustomLabel": True,
        "label": expression,
        "optionName": "metric_" + uuid.uuid5(NAMESPACE, expression).hex[:18],
    }


def adhoc_filter(spec: list[Any]) -> dict[str, Any]:
    column, operator, value = spec
    return {
        "clause": "WHERE",
        "subject": column,
        "operator": operator,
        "comparator": value,
        "expressionType": "SIMPLE",
    }


def chart_params(spec: dict[str, Any], dataset_id: int, dashboard_id: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "datasource": f"{dataset_id}__table",
        "adhoc_filters": [adhoc_filter(item) for item in spec.get("filters", [])],
        "row_limit": 10000,
        "color_scheme": "supersetColors",
        "extra_form_data": {},
        "dashboards": [dashboard_id],
    }
    viz = spec["viz"]
    if viz == "big_number_total":
        base.update(
            {
                "viz_type": "big_number_total",
                "metric": sql_metric(spec["metric"]),
                "header_font_size": 0.32,
                "subtitle_font_size": 0.13,
                "y_axis_format": "SMART_NUMBER",
                "conditional_formatting": [],
            }
        )
    elif viz == "bar":
        base.update(
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": spec["x"],
                "metrics": [sql_metric(item) for item in spec["metrics"]],
                "groupby": spec.get("groupby", []),
                "orientation": "horizontal" if spec.get("horizontal") else "vertical",
                "show_legend": True,
                "legendType": "scroll",
                "legendOrientation": "top",
                "truncateXAxis": True,
                "rich_tooltip": True,
                "y_axis_format": "SMART_NUMBER",
                "sort_series_type": "sum",
                "only_total": True,
            }
        )
    elif viz == "pie":
        base.update(
            {
                "viz_type": "pie",
                "groupby": [spec["dimension"]],
                "metric": sql_metric(spec["metric"]),
                "donut": True,
                "show_legend": True,
                "legendType": "scroll",
                "show_labels_threshold": 5,
                "label_type": "key_percent",
                "number_format": "SMART_NUMBER",
            }
        )
    elif viz == "heatmap":
        base.update(
            {
                "viz_type": "heatmap_v2",
                "all_columns_x": spec["x"],
                "all_columns_y": spec["y"],
                "metric": sql_metric(spec["metric"]),
                "linear_color_scheme": "blue_white_yellow",
                "normalize_across": None,
                "left_margin": "auto",
                "bottom_margin": "auto",
                "show_legend": True,
                "show_values": True,
                "y_axis_format": "SMART_NUMBER",
            }
        )
    elif viz == "table":
        base.update(
            {
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": spec["columns"],
                "order_by_cols": [],
                "server_pagination": False,
                "include_search": True,
                "page_length": 25,
            }
        )
    else:
        raise ValueError(f"Unsupported chart type: {viz}")
    return base


def upsert_dataset(
    conn: sqlite3.Connection,
    dataset: dict[str, Any],
    database_id: int,
    database_name: str,
    schema: str,
    owner_id: int,
) -> int:
    stamp = now()
    name = dataset["name"]
    row = conn.execute(
        "SELECT id FROM tables WHERE table_name=? AND database_id=? AND schema=?",
        (name, database_id, schema),
    ).fetchone()
    sql = (ROOT / "sql" / f"{name}.sql").read_text().strip().rstrip(";")
    if row:
        dataset_id = row[0]
        conn.execute(
            """UPDATE tables SET changed_on=?,changed_by_fk=?,description=?,sql=?,
               filter_select_enabled=1,is_sqllab_view=0,cache_timeout=0,
               is_managed_externally=0 WHERE id=?""",
            (stamp, owner_id, dataset["description"], sql, dataset_id),
        )
    else:
        dataset_id = next_id(conn, "tables")
        conn.execute(
            """INSERT INTO tables
               (created_on,changed_on,id,table_name,database_id,created_by_fk,changed_by_fk,
                description,cache_timeout,schema,sql,filter_select_enabled,is_sqllab_view,
                uuid,is_managed_externally,normalize_columns,always_filter_main_dttm)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stamp,
                stamp,
                dataset_id,
                name,
                database_id,
                owner_id,
                owner_id,
                dataset["description"],
                0,
                schema,
                sql,
                1,
                0,
                stable_uuid("dataset", name),
                0,
                0,
                0,
            ),
        )
    perm = f"[{database_name}].[{name}](id:{dataset_id})"
    schema_perm = f"[{database_name}].[{schema}]"
    conn.execute("UPDATE tables SET perm=?,schema_perm=? WHERE id=?", (perm, schema_perm, dataset_id))
    conn.execute("DELETE FROM table_columns WHERE table_id=?", (dataset_id,))
    for column_name, column_type in dataset["columns"].items():
        conn.execute(
            """INSERT INTO table_columns
               (created_on,changed_on,id,table_id,column_name,is_dttm,is_active,type,
                groupby,filterable,created_by_fk,changed_by_fk,uuid)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stamp,
                stamp,
                next_id(conn, "table_columns"),
                dataset_id,
                column_name,
                1 if column_type in {"DATE", "DATETIME", "TIMESTAMP"} else 0,
                1,
                column_type,
                1,
                1,
                owner_id,
                owner_id,
                stable_uuid("column", f"{name}.{column_name}"),
            ),
        )
    conn.execute("DELETE FROM sqlatable_user WHERE table_id=?", (dataset_id,))
    conn.execute(
        "INSERT INTO sqlatable_user (id,user_id,table_id) VALUES (?,?,?)",
        (next_id(conn, "sqlatable_user"), owner_id, dataset_id),
    )
    return dataset_id


def upsert_dashboard_shell(conn: sqlite3.Connection, owner_id: int) -> int:
    stamp = now()
    row = conn.execute("SELECT id FROM dashboards WHERE slug=?", (DASHBOARD_SLUG,)).fetchone()
    if row:
        dashboard_id = row[0]
        if dashboard_id == 5:
            raise RuntimeError("Refusing to modify protected dashboard id 5")
        conn.execute(
            """UPDATE dashboards SET changed_on=?,changed_by_fk=?,dashboard_title=?,
               description=?,published=1,is_managed_externally=0 WHERE id=?""",
            (
                stamp,
                owner_id,
                DASHBOARD_TITLE,
                "Governed, aggregate-only CCD supervisory dashboard. / 受管控的共同客戶匯總儀表板。",
                dashboard_id,
            ),
        )
    else:
        dashboard_id = next_id(conn, "dashboards")
        if dashboard_id == 5:
            raise RuntimeError("Refusing to allocate protected dashboard id 5")
        conn.execute(
            """INSERT INTO dashboards
               (created_on,changed_on,id,dashboard_title,created_by_fk,changed_by_fk,
                description,slug,published,uuid,is_managed_externally)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stamp,
                stamp,
                dashboard_id,
                DASHBOARD_TITLE,
                owner_id,
                owner_id,
                "Governed, aggregate-only CCD supervisory dashboard. / 受管控的共同客戶匯總儀表板。",
                DASHBOARD_SLUG,
                1,
                stable_uuid("dashboard", DASHBOARD_SLUG),
                0,
            ),
        )
    conn.execute("DELETE FROM dashboard_user WHERE dashboard_id=?", (dashboard_id,))
    conn.execute(
        "INSERT INTO dashboard_user (id,user_id,dashboard_id) VALUES (?,?,?)",
        (next_id(conn, "dashboard_user"), owner_id, dashboard_id),
    )
    return dashboard_id


def upsert_chart(
    conn: sqlite3.Connection,
    spec: dict[str, Any],
    dataset_id: int,
    dataset_name: str,
    database_name: str,
    schema: str,
    dashboard_id: int,
    owner_id: int,
) -> int:
    stamp = now()
    chart_uuid = stable_uuid("chart", spec["key"])
    row = conn.execute("SELECT id FROM slices WHERE uuid=?", (chart_uuid,)).fetchone()
    params = json.dumps(chart_params(spec, dataset_id, dashboard_id), separators=(",", ":"))
    datasource_name = f"{schema}.{dataset_name}"
    perm = f"[{database_name}].[{dataset_name}](id:{dataset_id})"
    schema_perm = f"[{database_name}].[{schema}]"
    if row:
        chart_id = row[0]
        conn.execute(
            """UPDATE slices SET changed_on=?,slice_name=?,datasource_type='table',
               datasource_name=?,viz_type=?,params=?,changed_by_fk=?,description=?,
               cache_timeout=0,perm=?,datasource_id=?,schema_perm=?,query_context=NULL,
               last_saved_at=?,last_saved_by_fk=?,is_managed_externally=0 WHERE id=?""",
            (
                stamp,
                spec["title"],
                datasource_name,
                chart_params(spec, dataset_id, dashboard_id)["viz_type"],
                params,
                owner_id,
                "Aggregate only; individual-level drill is intentionally unavailable.",
                perm,
                dataset_id,
                schema_perm,
                stamp,
                owner_id,
                chart_id,
            ),
        )
    else:
        chart_id = next_id(conn, "slices")
        conn.execute(
            """INSERT INTO slices
               (created_on,changed_on,id,slice_name,datasource_type,datasource_name,viz_type,
                params,created_by_fk,changed_by_fk,description,cache_timeout,perm,datasource_id,
                schema_perm,uuid,last_saved_at,last_saved_by_fk,is_managed_externally)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stamp,
                stamp,
                chart_id,
                spec["title"],
                "table",
                datasource_name,
                chart_params(spec, dataset_id, dashboard_id)["viz_type"],
                params,
                owner_id,
                owner_id,
                "Aggregate only; individual-level drill is intentionally unavailable.",
                0,
                perm,
                dataset_id,
                schema_perm,
                chart_uuid,
                stamp,
                owner_id,
                0,
            ),
        )
    conn.execute("DELETE FROM slice_user WHERE slice_id=?", (chart_id,))
    conn.execute(
        "INSERT INTO slice_user (id,user_id,slice_id) VALUES (?,?,?)",
        (next_id(conn, "slice_user"), owner_id, chart_id),
    )
    return chart_id


TAB_DEFINITIONS = [
    ("summary", "Summary / 總覽"),
    ("services", "Services / 服務"),
    ("identity", "Identity Resolution / 身份解析"),
    ("quality", "Data Quality / 數據質量"),
]

TAB_NOTES = {
    "summary": (
        "### Governed logical-person totals / 受管控邏輯客戶總數\n"
        "Counts use only included sources. Current Active or Needs Revalidation memberships collapse to one person; "
        "ended groups and pending workflow records do not. No client identifiers, contacts, or raw addresses are exposed."
    ),
    "services": (
        "### Service presence / 服務分佈\n"
        "A multi-service person counts once globally and once in every applicable service, so service totals can exceed "
        "the global distinct total. Availability dates describe centre capability, not client enrolment."
    ),
    "identity": (
        "### Global governed state / 全域受管控狀態\n"
        "This tab deliberately ignores Environment, Service, and Source filters. Proposed recommendations, Splink "
        "candidates, exceptions, and unfinished component reviews remain separate clients until current memberships exist."
    ),
    "quality": (
        "### Readiness before inference / 推論前的資料準備度\n"
        "Unknown, invalid, conflicting, excluded, and unclassified values remain visible. A stored sex placeholder is not "
        "trusted unless the current registration explicitly maps the sex field."
    ),
}


def build_position(chart_specs: list[dict[str, Any]], chart_ids: dict[str, int]) -> dict[str, Any]:
    position: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": DASHBOARD_TITLE}},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "parents": ["ROOT_ID"], "children": ["TABS-CCD"]},
        "TABS-CCD": {
            "id": "TABS-CCD",
            "type": "TABS",
            "parents": ["ROOT_ID", "GRID_ID"],
            "children": [f"TAB-{key}" for key, _ in TAB_DEFINITIONS],
            "meta": {},
        },
    }
    specs_by_tab = {key: [item for item in chart_specs if item["tab"] == key] for key, _ in TAB_DEFINITIONS}
    width_patterns = {
        "summary": [2, 2, 2, 2, 2, 2, 12, 6, 6, 12],
        "services": [8, 4, 4, 8, 12, 12],
        "identity": [6, 6, 12, 12],
        "quality": [4, 8, 12, 12],
    }
    for tab_key, tab_title in TAB_DEFINITIONS:
        tab_id = f"TAB-{tab_key}"
        parent_chain = ["ROOT_ID", "GRID_ID", "TABS-CCD"]
        note_id = f"MARKDOWN-{tab_key}-note"
        children = [note_id]
        position[tab_id] = {
            "id": tab_id,
            "type": "TAB",
            "parents": parent_chain,
            "children": children,
            "meta": {"text": tab_title, "defaultText": tab_title, "placeholder": "Tab title"},
        }
        position[note_id] = {
            "id": note_id,
            "type": "MARKDOWN",
            "parents": parent_chain + [tab_id],
            "children": [],
            "meta": {"code": TAB_NOTES[tab_key], "height": 8, "width": 12},
        }
        row_index = 0
        current_width = 0
        current_row_id = ""
        for index, spec in enumerate(specs_by_tab[tab_key]):
            width = width_patterns[tab_key][index]
            if not current_row_id or current_width + width > 12:
                row_index += 1
                current_width = 0
                current_row_id = f"ROW-{tab_key}-{row_index}"
                children.append(current_row_id)
                position[current_row_id] = {
                    "id": current_row_id,
                    "type": "ROW",
                    "parents": parent_chain + [tab_id],
                    "children": [],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"},
                }
            chart_id = chart_ids[spec["key"]]
            component_id = f"CHART-{spec['key']}"
            position[current_row_id]["children"].append(component_id)
            position[component_id] = {
                "id": component_id,
                "type": "CHART",
                "parents": parent_chain + [tab_id, current_row_id],
                "children": [],
                "meta": {
                    "chartId": chart_id,
                    "sliceName": spec["title"],
                    "uuid": str(uuid.UUID(bytes=stable_uuid("chart", spec["key"]))),
                    "height": 28 if width < 12 else 34,
                    "width": width,
                },
            }
            current_width += width
        if tab_key == "summary":
            growth_id = "MARKDOWN-growth-unavailable"
            growth_row = "ROW-summary-growth"
            children.append(growth_row)
            position[growth_row] = {
                "id": growth_row,
                "type": "ROW",
                "parents": parent_chain + [tab_id],
                "children": [growth_id],
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            }
            position[growth_id] = {
                "id": growth_id,
                "type": "MARKDOWN",
                "parents": parent_chain + [tab_id, growth_row],
                "children": [],
                "meta": {
                    "code": (
                        "### New User Growth / 新客戶增長 — Unavailable / 尚未提供\n"
                        "A governed `custom_service_start_date` and adequate retained history do not yet exist. "
                        "Registration creation dates are not substituted because that would be misleading."
                    ),
                    "height": 10,
                    "width": 12,
                },
            }
    return position


def filter_config(
    dataset_ids: dict[str, int],
    chart_specs: list[dict[str, Any]],
    chart_ids: dict[str, int],
) -> list[dict[str, Any]]:
    nonglobal = [chart_ids[item["key"]] for item in chart_specs if not item.get("global")]
    person_charts = [
        chart_ids[item["key"]]
        for item in chart_specs
        if not item.get("global") and item["dataset"] == "ccd_person_service_presence"
    ]
    source_charts = [
        chart_ids[item["key"]]
        for item in chart_specs
        if not item.get("global") and item["dataset"] in {"ccd_person_service_presence", "ccd_data_quality"}
    ]
    common_control = {
        "sortAscending": True,
        "enableEmptyFilter": True,
        "defaultToFirstItem": False,
        "multiSelect": True,
        "searchAllOptions": True,
        "inverseSelection": False,
    }
    env_id = "NATIVE_FILTER-CCD-ENVIRONMENT"
    service_id = "NATIVE_FILTER-CCD-SERVICE"
    source_id = "NATIVE_FILTER-CCD-SOURCE"
    return [
        {
            "id": env_id,
            "controlValues": common_control,
            "name": "Environment / 環境",
            "filterType": "filter_select",
            "targets": [
                {"column": {"name": "environment"}, "datasetId": dataset_ids["ccd_person_service_presence"]},
                {"column": {"name": "environment"}, "datasetId": dataset_ids["ccd_service_overlap"]},
                {"column": {"name": "environment"}, "datasetId": dataset_ids["ccd_data_quality"]},
            ],
            "defaultDataMask": {
                "extraFormData": {"filters": [{"col": "environment", "op": "IN", "val": ["Production"]}]},
                "filterState": {
                    "label": "Production",
                    "value": ["Production"],
                    "validateMessage": False,
                    "validateStatus": False,
                },
                "ownState": {},
            },
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
            "description": "Defaults to Production. Clear the selection for All.",
            "chartsInScope": nonglobal,
        },
        {
            "id": service_id,
            "controlValues": common_control,
            "name": "Service / 服務",
            "filterType": "filter_select",
            "targets": [
                {"column": {"name": "service"}, "datasetId": dataset_ids["ccd_person_service_presence"]}
            ],
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [env_id],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
            "description": "Options follow the Environment selection.",
            "chartsInScope": person_charts,
        },
        {
            "id": source_id,
            "controlValues": common_control,
            "name": "Source / 來源",
            "filterType": "filter_select",
            "targets": [
                {"column": {"name": "source"}, "datasetId": dataset_ids["ccd_person_service_presence"]},
                {"column": {"name": "source"}, "datasetId": dataset_ids["ccd_data_quality"]},
            ],
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [env_id, service_id],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
            "description": "Options follow Environment and Service.",
            "chartsInScope": source_charts,
        },
    ]


CSS = """
.dashboard-header { border-bottom: 3px solid #0f766e; }
.dashboard-component-tabs .ant-tabs-tab-active { color: #0f5f73 !important; }
.dashboard-component-chart-holder { border: 1px solid #dbe8ea; border-radius: 8px; }
.dashboard-markdown h3 { color: #124e66; margin-bottom: 6px; }
.dashboard-markdown { color: #334155; }
""".strip()


BASE_PERMISSIONS = [
    ("can_dashboard", "Superset"),
    ("can_explore", "Superset"),
    ("can_explore_json", "Superset"),
    ("can_fetch_datasource_metadata", "Superset"),
    ("can_language_pack", "Superset"),
    ("can_log", "Superset"),
    ("can_query", "Api"),
    ("can_query_form_data", "Api"),
    ("can_time_range", "Api"),
    ("can_get", "Datasource"),
    ("can_read", "Chart"),
    ("can_read", "Dashboard"),
    ("can_read", "DashboardFilterStateRestApi"),
    ("can_read", "Dataset"),
    ("can_read", "Database"),
    ("can_read", "Explore"),
    ("can_read", "ExploreFormDataRestApi"),
    ("can_read", "CurrentUserRestApi"),
    ("can_read", "SecurityRestApi"),
    ("can_write", "ExploreFormDataRestApi"),
    ("can_get", "MenuApi"),
    ("can_userinfo", "UserDBModelView"),
    ("menu_access", "Dashboards"),
    ("menu_access", "Home"),
]


def ensure_permission_view(conn: sqlite3.Connection, permission: str, view: str) -> int:
    row = conn.execute("SELECT id FROM ab_permission WHERE name=?", (permission,)).fetchone()
    if row:
        permission_id = row[0]
    else:
        permission_id = next_id(conn, "ab_permission")
        conn.execute("INSERT INTO ab_permission (id,name) VALUES (?,?)", (permission_id, permission))
    row = conn.execute("SELECT id FROM ab_view_menu WHERE name=?", (view,)).fetchone()
    if row:
        view_id = row[0]
    else:
        view_id = next_id(conn, "ab_view_menu")
        conn.execute("INSERT INTO ab_view_menu (id,name) VALUES (?,?)", (view_id, view))
    row = conn.execute(
        "SELECT id FROM ab_permission_view WHERE permission_id=? AND view_menu_id=?",
        (permission_id, view_id),
    ).fetchone()
    if row:
        return row[0]
    permission_view_id = next_id(conn, "ab_permission_view")
    conn.execute(
        "INSERT INTO ab_permission_view (id,permission_id,view_menu_id) VALUES (?,?,?)",
        (permission_view_id, permission_id, view_id),
    )
    return permission_view_id


def configure_role(
    conn: sqlite3.Connection,
    dashboard_id: int,
    dataset_ids: dict[str, int],
    database_name: str,
) -> int:
    row = conn.execute("SELECT id FROM ab_role WHERE name=?", (VIEWER_ROLE,)).fetchone()
    if row:
        role_id = row[0]
    else:
        role_id = next_id(conn, "ab_role")
        conn.execute("INSERT INTO ab_role (id,name) VALUES (?,?)", (role_id, VIEWER_ROLE))
    conn.execute("DELETE FROM ab_permission_view_role WHERE role_id=?", (role_id,))
    permission_views = [ensure_permission_view(conn, permission, view) for permission, view in BASE_PERMISSIONS]
    for name, dataset_id in dataset_ids.items():
        permission_views.append(
            ensure_permission_view(conn, "datasource_access", f"[{database_name}].[{name}](id:{dataset_id})")
        )
    for permission_view_id in sorted(set(permission_views)):
        conn.execute(
            "INSERT INTO ab_permission_view_role (id,permission_view_id,role_id) VALUES (?,?,?)",
            (next_id(conn, "ab_permission_view_role"), permission_view_id, role_id),
        )
    conn.execute("DELETE FROM dashboard_roles WHERE dashboard_id=? AND role_id=?", (dashboard_id, role_id))
    conn.execute(
        "INSERT INTO dashboard_roles (id,role_id,dashboard_id) VALUES (?,?,?)",
        (next_id(conn, "dashboard_roles"), role_id, dashboard_id),
    )
    return role_id


def finalize_gest_ai_access(conn: sqlite3.Connection, owner_id: int) -> None:
    alpha = conn.execute("SELECT id FROM ab_role WHERE name='Alpha'").fetchone()
    admin = conn.execute("SELECT id FROM ab_role WHERE name='Admin'").fetchone()
    if not alpha or not admin:
        raise RuntimeError("Expected Alpha and Admin roles are missing")
    conn.execute(
        "INSERT OR IGNORE INTO ab_user_role (id,user_id,role_id) VALUES (?,?,?)",
        (next_id(conn, "ab_user_role"), owner_id, alpha[0]),
    )
    conn.execute("DELETE FROM ab_user_role WHERE user_id=? AND role_id=?", (owner_id, admin[0]))


def install(args: argparse.Namespace) -> dict[str, Any]:
    conn = sqlite3.connect(args.metadata_db)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        before_dashboard5 = conn.execute(
            "SELECT dashboard_title,slug,position_json,json_metadata FROM dashboards WHERE id=5"
        ).fetchone()
        owner = conn.execute("SELECT id FROM ab_user WHERE username=?", (args.owner,)).fetchone()
        database = conn.execute("SELECT database_name FROM dbs WHERE id=?", (args.database_id,)).fetchone()
        if not owner or not database:
            raise RuntimeError("Owner or database id does not exist")
        owner_id = owner[0]
        database_name = database[0]
        schema = args.schema
        if not schema:
            row = conn.execute("SELECT schema FROM tables WHERE id=48").fetchone()
            if not row or not row[0]:
                raise RuntimeError("Schema was not supplied and could not be inferred")
            schema = row[0]
        datasets = load_json("datasets.json")
        dataset_ids = {
            item["name"]: upsert_dataset(conn, item, args.database_id, database_name, schema, owner_id)
            for item in datasets
        }
        dashboard_id = upsert_dashboard_shell(conn, owner_id)
        chart_specs = load_json("charts.json")
        chart_ids = {
            item["key"]: upsert_chart(
                conn,
                item,
                dataset_ids[item["dataset"]],
                item["dataset"],
                database_name,
                schema,
                dashboard_id,
                owner_id,
            )
            for item in chart_specs
        }
        conn.execute("DELETE FROM dashboard_slices WHERE dashboard_id=?", (dashboard_id,))
        for chart_id in chart_ids.values():
            conn.execute(
                "INSERT INTO dashboard_slices (id,dashboard_id,slice_id) VALUES (?,?,?)",
                (next_id(conn, "dashboard_slices"), dashboard_id, chart_id),
            )
        position = build_position(chart_specs, chart_ids)
        global_chart_ids = [chart_ids[item["key"]] for item in chart_specs if item.get("global")]
        metadata = {
            "chart_configuration": {},
            "global_chart_configuration": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": list(chart_ids.values()),
            },
            "native_filter_configuration": filter_config(dataset_ids, chart_specs, chart_ids),
            "color_scheme": "supersetColors",
            "refresh_frequency": 0,
            "expanded_slices": {},
            "label_colors": {},
            "timed_refresh_immune_slices": list(chart_ids.values()),
            "cross_filters_enabled": False,
            "default_filters": "{}",
            "show_chart_timestamps": True,
            "ccd_global_identity_charts": global_chart_ids,
        }
        conn.execute(
            "UPDATE dashboards SET position_json=?,json_metadata=?,css=? WHERE id=?",
            (
                json.dumps(position, separators=(",", ":"), ensure_ascii=False),
                json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
                CSS,
                dashboard_id,
            ),
        )
        role_id = configure_role(conn, dashboard_id, dataset_ids, database_name)
        if args.finalize_access:
            finalize_gest_ai_access(conn, owner_id)
        after_dashboard5 = conn.execute(
            "SELECT dashboard_title,slug,position_json,json_metadata FROM dashboards WHERE id=5"
        ).fetchone()
        if before_dashboard5 != after_dashboard5:
            raise RuntimeError("Protected dashboard id 5 changed; rolling back")
        conn.commit()
        return {
            "dashboard_id": dashboard_id,
            "dashboard_slug": DASHBOARD_SLUG,
            "dataset_ids": dataset_ids,
            "chart_count": len(chart_ids),
            "viewer_role_id": role_id,
            "gest_ai_admin_removed": bool(args.finalize_access),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-db", required=True, type=Path)
    parser.add_argument("--database-id", type=int, default=1)
    parser.add_argument("--schema")
    parser.add_argument("--owner", default="gest-ai")
    parser.add_argument("--finalize-access", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(install(parse_args()), indent=2, sort_keys=True))

