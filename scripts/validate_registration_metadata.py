"""Read-only validation for CCD Registration dashboard metadata.

Run from a Frappe console:

    exec(open("scripts/validate_registration_metadata.py").read(), globals())
"""

from __future__ import annotations

import json

import frappe


EXPECTED_ENVIRONMENTS = {
    "HQ-vDB01_HMSSHP_Prod": "Production",
    "HQ-vDB01_DHCE_Prod": "Production",
    "HQ-vDB01_HKSReCCMS_PROD": "Production",
    "HQ-vDB01_pjCHW": "Production",
    "SHP-DB-UAT_HMSSHP_UAT": "UAT",
    "PHI-vDBUAT_HMSPhi_UAT": "UAT",
    "SHP-DB-UAT_SHPMoodle_UAT": "UAT",
    "PHI-vDBUAT_HMSPhi_SIT": "SIT",
    "DT-NB10_event-management": "Development",
    "DT-NB10_maxdb": "Development",
}

EXPECTED_FIELDS = {
    "custom_dashboard_metadata_section": ("Section Break", 1),
    "custom_include_in_dashboard": ("Check", 1),
    "custom_dashboard_environment": ("Select", 1),
    "custom_service_available_from": ("Date", 1),
}


def root_name(registration_name: str, amended_from: str | None) -> str:
    current = registration_name
    parent = amended_from
    seen = {current}
    while parent and parent not in seen:
        seen.add(parent)
        current = parent
        parent = frappe.db.get_value("CCD Registration", parent, "amended_from")
    return current


def validate() -> dict[str, object]:
    fields = frappe.get_all(
        "Custom Field",
        filters={
            "dt": "CCD Registration",
            "fieldname": ["in", list(EXPECTED_FIELDS)],
        },
        fields=["fieldname", "fieldtype", "allow_on_submit", "default", "options"],
    )
    by_name = {row.fieldname: row for row in fields}
    assert set(by_name) == set(EXPECTED_FIELDS)
    for fieldname, (fieldtype, allow_on_submit) in EXPECTED_FIELDS.items():
        row = by_name[fieldname]
        assert row.fieldtype == fieldtype
        assert int(row.allow_on_submit or 0) == allow_on_submit
    assert str(by_name["custom_include_in_dashboard"].default or "0") == "0"
    select_options = set((by_name["custom_dashboard_environment"].options or "").splitlines())
    assert {"Production", "UAT", "SIT", "Development", "Test"}.issubset(select_options)

    registrations = frappe.get_all(
        "CCD Registration",
        filters={"docstatus": 1},
        fields=[
            "name",
            "amended_from",
            "custom_include_in_dashboard",
            "custom_dashboard_environment",
        ],
    )
    classified = []
    for row in registrations:
        root = root_name(row.name, row.amended_from)
        expected = EXPECTED_ENVIRONMENTS.get(root)
        if expected is None:
            continue
        assert int(row.custom_include_in_dashboard or 0) == 1
        assert row.custom_dashboard_environment == expected
        classified.append((root, expected))
    assert dict(classified) == EXPECTED_ENVIRONMENTS

    result = {
        "custom_fields_valid": len(fields),
        "classified_current_sources": len(classified),
        "environments": sorted(set(EXPECTED_ENVIRONMENTS.values())),
    }
    print(json.dumps(result, sort_keys=True))
    return result


validate()
