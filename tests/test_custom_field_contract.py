from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_fields_are_editable_after_submit_and_default_excluded():
    source = (ROOT / "scripts" / "install_custom_fields.py").read_text()
    assert '"custom_include_in_dashboard"' in source
    assert source.count('"custom_service_start_date"') == 2
    assert '"CCD Master"' in source
    assert '"default": "0"' in source
    assert source.count('"allow_on_submit": 1') >= 5
    assert "Production\\nUAT\\nSIT\\nDevelopment\\nTest" in source


def test_growth_readiness_uses_client_level_service_start_coverage():
    sql = (ROOT / "sql" / "ccd_data_quality.sql").read_text()
    charts = (ROOT / "manifests" / "charts.json").read_text()
    assert "m.custom_service_start_date IS NOT NULL" in sql
    assert "service_start_populated_rows" in sql
    assert "service start dates not populated" in sql
    assert "custom_service_start_date not installed" not in sql
    assert "service_start_coverage_pct" in charts


def test_all_initial_included_sources_are_seeded():
    source = (ROOT / "scripts" / "install_custom_fields.py").read_text()
    expected = {
        "HQ-vDB01_HMSSHP_Prod",
        "HQ-vDB01_DHCE_Prod",
        "HQ-vDB01_HKSReCCMS_PROD",
        "HQ-vDB01_pjCHW",
        "SHP-DB-UAT_HMSSHP_UAT",
        "PHI-vDBUAT_HMSPhi_UAT",
        "SHP-DB-UAT_SHPMoodle_UAT",
        "PHI-vDBUAT_HMSPhi_SIT",
        "DT-NB10_event-management",
        "DT-NB10_maxdb",
    }
    assert all(name in source for name in expected)
