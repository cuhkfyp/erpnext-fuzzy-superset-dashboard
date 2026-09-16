#!/usr/bin/env python3
"""Execute every installed governed chart through Superset's query engine."""

from __future__ import annotations

import json
import time

from flask import g
from flask_login import login_user

from superset.app import create_app


REQUIRED_CHARTS = {
    "Logical Clients / 邏輯客戶",
    "New Logical Clients by Month / 每月新增邏輯客戶",
    "New Clients by Service and Month / 按服務每月新增客戶",
    "Age Distribution and Confidence / 年齡及可信度",
    "Hong Kong Client Distribution / 香港客戶地區分佈",
    "Confirmed Interconnectivity / 已確認互聯",
    "Pending Workflow Pipelines / 待處理工作流程",
    "Data Quality Warnings / 數據質量警告",
    "Source Readiness Detail / 來源準備詳情",
}


def query_object(params):
    viz_type = params["viz_type"]
    columns = []
    metrics = []
    if viz_type == "big_number_total":
        metrics = [params["metric"]]
    elif viz_type == "echarts_timeseries_bar":
        columns = [params["x_axis"], *params.get("groupby", [])]
        metrics = params["metrics"]
    elif viz_type == "pie":
        columns = params["groupby"]
        metrics = [params["metric"]]
    elif viz_type == "heatmap_v2":
        columns = [params["all_columns_x"], params["all_columns_y"]]
        metrics = [params["metric"]]
    elif viz_type == "chord":
        columns = [params["groupby"], params["columns"]]
        metrics = [params["metric"]]
    elif viz_type == "deck_polygon":
        columns = [params["line_column"], *params.get("tooltip_contents", [])]
        metrics = [params["metric"]]
    elif viz_type == "table":
        columns = params["all_columns"]
    else:
        raise ValueError(viz_type)
    filters = [
        {"col": item["subject"], "op": item["operator"], "val": item["comparator"]}
        for item in params.get("adhoc_filters", [])
    ]
    return {
        "columns": columns,
        "metrics": metrics,
        "orderby": [],
        "row_limit": params.get("row_limit", 10000),
        "filters": filters,
        "time_range": "No filter",
    }


app = create_app()
from superset.commands.chart.data.get_data_command import ChartDataCommand
from superset.common.query_context_factory import QueryContextFactory
from superset.extensions import db
from superset.models.dashboard import Dashboard
from superset.models.slice import Slice

with app.test_request_context("/api/v1/chart/data"):
    user = app.appbuilder.sm.find_user(username="gest-ai")
    if not user:
        raise RuntimeError("gest-ai user not found")
    login_user(user)
    g.user = user
    dashboard = (
        db.session.query(Dashboard)
        .filter(Dashboard.slug == "common-client-database-governed")
        .one()
    )
    charts = sorted(dashboard.slices, key=lambda chart: chart.id)
    installed_names = {chart.slice_name for chart in charts}
    if len(charts) != 26 or not REQUIRED_CHARTS.issubset(installed_names):
        raise RuntimeError("Installed governed dashboard chart set is incomplete")
    summary = []
    for chart in charts:
        params = json.loads(chart.params)
        query = query_object(params)
        if chart.datasource.table_name in {
            "ccd_person_service_presence",
            "ccd_district_map",
            "ccd_service_overlap",
            "ccd_data_quality",
        }:
            query["filters"].append({"col": "environment", "op": "IN", "val": ["Production"]})
        started = time.monotonic()
        context = QueryContextFactory().create(
            datasource={"id": chart.datasource_id, "type": "table"},
            queries=[query],
            form_data=params,
        )
        command = ChartDataCommand(context)
        command.validate()
        payload = command.run()
        query_result = payload["queries"][0]
        if query_result.get("error"):
            raise RuntimeError(f"{chart.slice_name}: {query_result['error']}")
        data = query_result.get("data") or []
        summary.append(
            {
                "chart_id": chart.id,
                "chart": chart.slice_name,
                "rows": len(data),
                "seconds": round(time.monotonic() - started, 3),
            }
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
