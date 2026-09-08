"""Read-only profiler for locating live-query cost; aggregate output only."""

import time

import frappe


queries = [
    ("raw", "SELECT COUNT(*) FROM `tabCCD Master`"),
    (
        "raw_production",
        "SELECT COUNT(*) FROM `tabCCD Master` WHERE ccd_reg_source IN "
        "('HQ-vDB01_HMSSHP_Prod','HQ-vDB01_DHCE_Prod','HQ-vDB01_HKSReCCMS_PROD','HQ-vDB01_pjCHW')",
    ),
    (
        "hash_distinct",
        "SELECT COUNT(DISTINCT SHA2(CONCAT('M:',name),256)) FROM `tabCCD Master` WHERE ccd_reg_source IN "
        "('HQ-vDB01_HMSSHP_Prod','HQ-vDB01_DHCE_Prod','HQ-vDB01_HKSReCCMS_PROD','HQ-vDB01_pjCHW')",
    ),
    (
        "dob_categories",
        "SELECT CASE WHEN birthday IS NULL THEN 'missing' WHEN birthday BETWEEN DATE_SUB(CURRENT_DATE,INTERVAL 120 YEAR) "
        "AND CURRENT_DATE THEN 'plausible' ELSE 'invalid' END,COUNT(*) FROM `tabCCD Master` WHERE ccd_reg_source IN "
        "('HQ-vDB01_HMSSHP_Prod','HQ-vDB01_DHCE_Prod','HQ-vDB01_HKSReCCMS_PROD','HQ-vDB01_pjCHW') GROUP BY 1",
    ),
    (
        "membership_join",
        "SELECT COUNT(DISTINCT COALESCE(im.identity_group,m.name)) FROM `tabCCD Master` m LEFT JOIN "
        "`tabCCD Identity Membership` im ON im.ccd_master=m.name AND im.status='Active' WHERE m.ccd_reg_source IN "
        "('HQ-vDB01_HMSSHP_Prod','HQ-vDB01_DHCE_Prod','HQ-vDB01_HKSReCCMS_PROD','HQ-vDB01_pjCHW')",
    ),
]
for label, query in queries:
    started = time.monotonic()
    result = frappe.db.sql(query)
    print(label, round(time.monotonic() - started, 3), result, flush=True)

