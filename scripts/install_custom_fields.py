"""Idempotent CCD Registration dashboard metadata installer.

Run from a Frappe console so no credentials are placed in this repository:

    exec(open("scripts/install_custom_fields.py").read(), globals())

The fields deliberately default to excluded.  Only the named initial sources are
seeded, and only on their current submitted amendment.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


ENVIRONMENT_BY_ROOT = {
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

CUSTOM_FIELDS = {
    "CCD Registration": [
        {
            "fieldname": "custom_dashboard_metadata_section",
            "label": "Dashboard Metadata / 儀表板資料",
            "fieldtype": "Section Break",
            "insert_after": "service_name",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_include_in_dashboard",
            "label": "Include in Dashboard / 納入儀表板",
            "fieldtype": "Check",
            "insert_after": "custom_dashboard_metadata_section",
            "default": "0",
            "allow_on_submit": 1,
            "description": "Official totals include this source only when enabled and classified.",
        },
        {
            "fieldname": "custom_dashboard_environment",
            "label": "Dashboard Environment / 儀表板環境",
            "fieldtype": "Select",
            "options": "\nProduction\nUAT\nSIT\nDevelopment\nTest",
            "insert_after": "custom_include_in_dashboard",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_service_available_from",
            "label": "Service Available From / 服務可提供日期",
            "fieldtype": "Date",
            "insert_after": "custom_dashboard_environment",
            "allow_on_submit": 1,
            "description": "Centre capability date; this is not a client enrolment date.",
        },
    ]
}


def _root_name(registration_name: str, amended_from: str | None) -> str:
    """Follow an amendment chain defensively and return its original name."""
    current = registration_name
    parent = amended_from
    seen = {current}
    while parent and parent not in seen:
        seen.add(parent)
        current = parent
        parent = frappe.db.get_value("CCD Registration", parent, "amended_from")
    return current


def install() -> dict[str, object]:
    create_custom_fields(CUSTOM_FIELDS, update=True)
    seeded: list[dict[str, str]] = []
    submitted = frappe.get_all(
        "CCD Registration",
        filters={"docstatus": 1},
        fields=["name", "amended_from"],
        order_by="modified desc",
    )
    for row in submitted:
        root = _root_name(row.name, row.amended_from)
        environment = ENVIRONMENT_BY_ROOT.get(root)
        if not environment:
            continue
        frappe.db.set_value(
            "CCD Registration",
            row.name,
            {
                "custom_include_in_dashboard": 1,
                "custom_dashboard_environment": environment,
            },
            update_modified=False,
        )
        seeded.append({"root": root, "current": row.name, "environment": environment})
    frappe.db.commit()
    result = {"field_count": 4, "seeded": seeded}
    print(result)
    return result


install()
