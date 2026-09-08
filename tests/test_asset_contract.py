import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_only_aggregate_safe_columns_are_exposed():
    datasets = json.loads((ROOT / "manifests" / "datasets.json").read_text())
    exposed = {column.lower() for dataset in datasets for column in dataset["columns"]}
    forbidden = {
        "name",
        "ccd_master",
        "identity_group",
        "hksr_num",
        "hkid",
        "bc_num",
        "email",
        "mobile",
        "phone_num",
        "res_addr1",
        "res_addr2",
        "res_addr3",
        "post_addr1",
        "post_addr2",
        "post_addr3",
    }
    assert forbidden.isdisjoint(exposed)


def test_raw_address_lines_are_never_read_or_parsed():
    sql = "\n".join(path.read_text().lower() for path in (ROOT / "sql").glob("*.sql"))
    for field in (
        "res_addr1",
        "res_addr2",
        "res_addr3",
        "post_addr1",
        "post_addr2",
        "post_addr3",
    ):
        assert field not in sql


def test_pending_workflows_do_not_collapse_people():
    sql = (ROOT / "sql" / "ccd_person_service_presence.sql").read_text().lower()
    assert "tabccd identity membership" in sql
    assert "tabccd identity group" in sql
    assert "tabccd match recommendation" not in sql
    assert "tabccd match review candidate" not in sql
    assert "tabccd identity exclusion" not in sql


def test_dashboard_defaults_and_global_identity_scope():
    dashboard = json.loads((ROOT / "manifests" / "dashboard.json").read_text())
    charts = json.loads((ROOT / "manifests" / "charts.json").read_text())
    assert dashboard["default_environment"] == "Production"
    assert dashboard["refresh_frequency_seconds"] == 0
    assert dashboard["protected_dashboard_id"] == 5
    assert len(dashboard["tabs"]) == 4
    identity = [item for item in charts if item["tab"] == "identity"]
    assert identity and all(item.get("global") is True for item in identity)


def test_viewer_role_has_no_sql_lab_raw_or_drill_permissions():
    source = (ROOT / "scripts" / "install_superset_assets.py").read_text()
    permissions_block = source.split("BASE_PERMISSIONS =", 1)[1].split("]", 1)[0]
    assert "SQLLab" not in permissions_block
    assert "can_drill" not in permissions_block
    assert "can_csv" not in permissions_block
    assert "(id:48)" not in permissions_block


def test_four_required_virtual_datasets_are_present():
    datasets = json.loads((ROOT / "manifests" / "datasets.json").read_text())
    assert {item["name"] for item in datasets} == {
        "ccd_person_service_presence",
        "ccd_service_overlap",
        "ccd_identity_operations",
        "ccd_data_quality",
    }

