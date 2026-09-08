#!/usr/bin/env python3
"""Execute representative installed charts through Superset's query engine."""

from __future__ import annotations

import json
import time

from flask import g
from flask_login import login_user

from superset.app import create_app


CHART_KEYS = {
    "Logical Clients / 邏輯客戶",
    "Age Distribution and Confidence / 年齡及可信度",
    "Confirmed Interconnectivity / 已確認互聯矩陣",
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
from superset.models.slice import Slice

with app.test_request_context("/api/v1/chart/data"):
    user = app.appbuilder.sm.find_user(username="gest-ai")
    if not user:
        raise RuntimeError("gest-ai user not found")
    login_user(user)
    g.user = user
    charts = (
        db.session.query(Slice)
        .filter(Slice.slice_name.in_(CHART_KEYS))
        .order_by(Slice.id)
        .all()
    )
    if {chart.slice_name for chart in charts} != CHART_KEYS:
        raise RuntimeError("Representative chart set is incomplete")
    summary = []
    for chart in charts:
        params = json.loads(chart.params)
        query = query_object(params)
        if chart.datasource.table_name in {"ccd_person_service_presence", "ccd_service_overlap"}:
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
