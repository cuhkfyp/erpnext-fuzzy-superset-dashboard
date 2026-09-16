"""Export a private, aggregate address-inference review sheet.

Run inside a connected Frappe console. The CSV deliberately contains no CCD
Master names, identity-group identifiers, person names, phone numbers, or
email fields. Exact address text is included only where human district review
is possible; the resulting file must remain mode 0600 and outside Git.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path


SQL_PATH = Path("/tmp/ccd_data_quality.sql")
OUTPUT_PATH = Path("/tmp/ccd_address_inference_review.csv")


quality_sql = SQL_PATH.read_text(encoding="utf-8")
quality_sql = quality_sql.replace(
    "/*__PRIVATE_ADDRESS_OVERRIDE_ROWS__*/",
    "SELECT NULL AS address_hash, NULL AS district_code WHERE 0",
)
cte_prefix, separator, _ = quality_sql.partition(",\naddress_quality AS (")
if not separator:
    raise RuntimeError("Could not locate the address-quality CTE boundary")

query = cte_prefix + r"""
,
address_match_codes AS (
    SELECT
        ac.master_name,
        GROUP_CONCAT(DISTINCT adp.district_code ORDER BY adp.district_code SEPARATOR '|')
            AS matched_district_codes
    FROM address_candidates ac
    LEFT JOIN address_district_patterns adp
      ON LOCATE(adp.address_token, ac.normalized_address) > 0
    GROUP BY ac.master_name
)
SELECT
    sm.environment,
    m.ccd_reg_source AS source,
    CASE
        WHEN lf.address_present = 0
         AND lf.residential_present = 0
         AND lf.postal_present = 0
            THEN 'Missing all location fields - cannot infer'
        WHEN lf.address_present = 0
            THEN 'Invalid district value and no address - cannot infer'
        WHEN COALESCE(amr.address_district_match_count, 0) > 1
            THEN 'Ambiguous - matched multiple districts'
        ELSE 'Unmatched address text - human review needed'
    END AS failure_reason,
    CASE WHEN lf.address_present = 1 THEN TRIM(m.res_addr1) ELSE '' END AS address_text,
    COALESCE(NULLIF(TRIM(m.res_district), ''), '') AS residential_district_value,
    COALESCE(NULLIF(TRIM(m.post_district), ''), '') AS postal_district_value,
    COALESCE(amc.matched_district_codes, '') AS matched_district_codes,
    COUNT(*) AS source_row_count
FROM `tabCCD Master` m
JOIN location_flags lf ON lf.master_name = m.name
JOIN source_metadata sm ON sm.source_name = m.ccd_reg_source
LEFT JOIN address_match_rollup amr ON amr.master_name = m.name
LEFT JOIN address_match_codes amc ON amc.master_name = m.name
WHERE sm.include_in_dashboard = 1
  AND sm.environment IN ('Production', 'UAT', 'SIT', 'Development', 'Test')
  AND lf.residential_valid = 0
  AND lf.postal_valid = 0
  AND (
      lf.address_present = 0
      OR COALESCE(amr.address_district_match_count, 0) <> 1
  )
GROUP BY
    sm.environment,
    m.ccd_reg_source,
    failure_reason,
    address_text,
    residential_district_value,
    postal_district_value,
    matched_district_codes
ORDER BY
    FIELD(failure_reason,
        'Ambiguous - matched multiple districts',
        'Unmatched address text - human review needed',
        'Invalid district value and no address - cannot infer',
        'Missing all location fields - cannot infer'),
    sm.environment,
    m.ccd_reg_source,
    source_row_count DESC,
    address_text
"""

rows = frappe.db.sql(query, as_dict=True)  # noqa: F821 - provided by Frappe console


def spreadsheet_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


fieldnames = [
    "environment",
    "source",
    "failure_reason",
    "address_text_private",
    "residential_district_value",
    "postal_district_value",
    "automatically_matched_district_codes",
    "source_row_count",
    "reviewer_district_code",
    "reviewer_note",
]

with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "environment": spreadsheet_safe(row.environment),
                "source": spreadsheet_safe(row.source),
                "failure_reason": spreadsheet_safe(row.failure_reason),
                "address_text_private": spreadsheet_safe(row.address_text),
                "residential_district_value": spreadsheet_safe(
                    row.residential_district_value
                ),
                "postal_district_value": spreadsheet_safe(row.postal_district_value),
                "automatically_matched_district_codes": spreadsheet_safe(
                    row.matched_district_codes
                ),
                "source_row_count": int(row.source_row_count),
                "reviewer_district_code": "",
                "reviewer_note": "",
            }
        )

os.chmod(OUTPUT_PATH, 0o600)

reason_rows = Counter()
reason_source_rows = Counter()
for row in rows:
    reason_rows[row.failure_reason] += 1
    reason_source_rows[row.failure_reason] += int(row.source_row_count)

print(
    json.dumps(
        {
            "output": str(OUTPUT_PATH),
            "mode": oct(OUTPUT_PATH.stat().st_mode & 0o777),
            "review_lines": len(rows),
            "distinct_lines_by_reason": dict(reason_rows),
            "source_rows_by_reason": dict(reason_source_rows),
        },
        ensure_ascii=False,
        indent=2,
    )
)
