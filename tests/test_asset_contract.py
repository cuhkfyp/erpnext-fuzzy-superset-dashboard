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


def test_only_residential_address_1_is_parsed_as_a_private_fallback():
    sql = "\n".join(path.read_text().lower() for path in (ROOT / "sql").glob("*.sql"))
    for field in (
        "res_addr2",
        "res_addr3",
        "post_addr1",
        "post_addr2",
        "post_addr3",
    ):
        assert field not in sql
    assert "res_addr1" in sql
    assert "address_district_patterns" in sql
    assert "district_match_count = 1" in sql


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


def test_required_virtual_datasets_are_present():
    datasets = json.loads((ROOT / "manifests" / "datasets.json").read_text())
    assert {item["name"] for item in datasets} == {
        "ccd_person_service_presence",
        "ccd_district_map",
        "ccd_service_overlap",
        "ccd_identity_operations",
        "ccd_data_quality",
    }


def test_primary_summary_counts_use_exact_integer_format():
    charts = {
        item["key"]: item
        for item in json.loads((ROOT / "manifests" / "charts.json").read_text())
    }
    assert charts["logical_clients"]["number_format"] == ",.0f"
    assert charts["source_rows"]["number_format"] == ",.0f"


def test_circle_charts_use_taller_compact_label_layout():
    installer = (ROOT / "scripts" / "install_superset_assets.py").read_text()
    assert '"label_type": "value"' in installer
    assert '"outerRadius": 55' in installer
    assert 'if spec["viz"] == "pie"' in installer
    assert 'if spec["viz"] in {"deck_polygon", "chord"}' in installer


def test_growth_chord_and_hong_kong_map_are_enabled():
    charts = {
        item["key"]: item
        for item in json.loads((ROOT / "manifests" / "charts.json").read_text())
    }
    assert charts["overall_growth"]["x"] == "overall_growth_month"
    assert charts["service_growth"]["x"] == "service_growth_month"
    assert charts["service_overlap"]["viz"] == "chord"
    assert charts["identity_composition"]["viz"] == "chord"
    assert charts["identity_composition"]["source"] == "status"
    assert charts["identity_composition"]["target"] == "detail"
    assert charts["district_distribution"]["viz"] == "deck_polygon"
    assert charts["district_distribution"]["geometry"] == "district_polygon"
    installer = (ROOT / "scripts" / "install_superset_assets.py").read_text()
    assert "MARKDOWN-growth-unavailable" not in installer


def test_official_district_geometry_has_all_18_controlled_codes():
    geometry = json.loads((ROOT / "assets" / "hk_districts_simplified.geojson").read_text())
    assert len(geometry["features"]) == 18
    codes = {item["properties"]["district_code"] for item in geometry["features"]}
    assert codes == {
        "CW", "EST", "SOU", "WC", "KC", "KWT", "SSP", "WTS", "YTM",
        "IS", "KUI", "NOR", "SK", "ST", "TP", "TW", "TM", "YL",
    }


def test_canonical_and_loopback_database_routes_are_managed():
    socket_unit = (ROOT / "deployment" / "hksr-mariadb-proxy.socket").read_text()
    proxy_unit = (ROOT / "deployment" / "hksr-mariadb-proxy.service").read_text()
    superset_unit = (ROOT / "deployment" / "hksr-superset.service").read_text()
    installer = (ROOT / "deployment" / "install_runtime.sh").read_text()
    repair = (ROOT / "scripts" / "repair_mysql_route.py").read_text()
    assert "ListenStream=127.0.0.1:3306" in socket_unit
    assert "erpnext_db:3306" in proxy_unit
    assert "hksr-mariadb-proxy.socket" in superset_unit
    assert "systemctl enable --now hksr-mariadb-proxy.socket" in installer
    assert 'parser.add_argument("--host", default="erpnext_db")' in repair
    assert "set_sqlalchemy_uri" in repair
    assert "SELECT 1" in repair


def test_managed_runtime_uses_current_certificate_and_retires_known_daemon():
    superset_unit = (ROOT / "deployment" / "hksr-superset.service").read_text()
    restart = (ROOT / "deployment" / "hksr-superset-restart.sh").read_text()
    assert "/superset/certs/fullchain.pem" in superset_unit
    assert "/superset/certs/hksr.org.hk.key" in superset_unit
    assert "openssl x509" in restart
    assert "find_unmanaged_gunicorn_pid" in restart
    assert "gunicorn -w 10 -k gevent" in restart
    assert "restore_unmanaged_gunicorn" in restart


def test_hong_kong_map_uses_maplibre_with_narrow_osm_csp_allowance():
    runtime = (ROOT / "deployment" / "superset_runtime_config.py").read_text()
    installer = (ROOT / "scripts" / "install_superset_assets.py").read_text()
    assert 'DEFAULT_MAP_RENDERER = "maplibre"' in runtime
    assert "tile://https://tile.openstreetmap.org/{z}/{x}/{y}.png" in runtime
    assert '"connect-src": ["\'self\'", "https://tile.openstreetmap.org"]' in runtime
    assert '"img-src": ["\'self\'", "data:", "blob:", "https://tile.openstreetmap.org"]' in runtime
    assert '"mapbox_style": "tile://https://tile.openstreetmap.org/{z}/{x}/{y}.png"' in installer
