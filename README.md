# Common Client Database / 共同客戶資料庫

Portable, aggregate-only assets for the governed CCD Superset dashboard. The
dashboard is a new object and the installer refuses to modify dashboard ID 5.

## What is installed

- Five live MariaDB virtual datasets under `sql/`.
- Twenty-six bilingual charts on Summary, Services, Identity Resolution, and
  Data Quality tabs.
- Cascading Environment → Service → Source filters. Production is the default;
  clearing Environment selects all included environments.
- `CCD Dashboard Viewer`, with dashboard/dataset read access but no SQL Lab,
  raw CCD Master, export, CSV, or individual-drill permissions.
- Four editable-after-submit CCD Registration metadata fields plus a bilingual
  section heading, and a client-level service-start date on CCD Master.
- A one-worker, bounded-thread Gunicorn systemd unit and a Superset-only restart
  path. The live cache is explicitly `NullCache` and refresh frequency is zero.
- A loopback-only compatibility proxy makes `127.0.0.1:3306` reach the same
  MariaDB service as the canonical `erpnext_db:3306` route. Superset itself uses
  the canonical alias so a missing temporary forward cannot break dashboards.
- A disabled, isolated Redis profile for a later capacity-reviewed release.

No database URI, password, token, certificate, Superset SQLite file, backup,
raw query result, client data, or screenshot is stored here.

## Deployment order

1. Verify a fresh ERPNext database backup and a compressed mode-0600 Superset
   SQLite backup with `PRAGMA integrity_check`.
2. Install fields from a Frappe console:

   ```python
   exec(open("scripts/install_custom_fields.py").read(), globals())
   ```

3. Validate the asset installer twice against a disposable metadata copy:

   ```bash
   python3 scripts/install_superset_assets.py --metadata-db /tmp/superset-validation.db
   python3 scripts/install_superset_assets.py --metadata-db /tmp/superset-validation.db
   ```

4. Install live metadata, initially without access finalization. Validate chart
   queries, ownership, role scope, and dashboard-5 hash. Then rerun with
   `--finalize-access` to remove only the Admin role from `gest-ai`; Alpha and
   ownership remain.
5. As root, run `deployment/install_runtime.sh`. It updates only Superset files,
   installs `hksr-superset.service` and the loopback-only MariaDB compatibility
   proxy, stops the exact legacy Superset process, and checks HTTPS `/health`.
   It does not invoke Docker or touch ERPNext, n8n, or either Redis deployment.
6. If a legacy Superset database record points at `127.0.0.1`, validate and
   restore its canonical route without printing credentials:

   ```bash
   python3 scripts/repair_mysql_route.py
   python3 scripts/repair_mysql_route.py --apply
   ```

## Governed counting behavior

Current Active and Needs Revalidation identity memberships collapse records to
one logical person. Ended memberships/groups and pending recommendation,
Splink, exception, or component-review rows do not. A multi-service person
counts once globally and once in every applicable service. Canonical DOB, sex,
and district categories preserve Unknown, Invalid, and Conflicting states.

The Services-tab **Confirmed Interconnectivity** chord is filter-aware. Its
links count logical people who have a current confirmed presence at both
endpoints in the selected environment. The Identity Resolution-tab **Group
Source Interconnectivity** chord is deliberately global: each current identity
group contributes once to every unordered pair of distinct sources represented
inside that group. Thus a group containing sources A, B, and C contributes one
group to A-B, A-C, and B-C; chord width is the number of current groups sharing
that source pair.

`custom_service_start_date` is installed on CCD Master for the actual client
service-enrolment date and on CCD Registration as optional source-level metadata.
Growth uses only CCD Master dates; it is never inferred from registration or
modification timestamps. Overall growth uses each logical person's earliest
populated service-start date, while service growth uses the first populated
date within each service. Missing dates remain excluded and their coverage is
reported in Data Quality.

The Hong Kong district map prioritizes a controlled residential district, then
a controlled postal district, then conservative bilingual token matching on
Residential Address 1. Address inference runs entirely inside MariaDB: raw
address text is neither projected by a dashboard dataset nor sent to Google or
another geocoding service. Ambiguous and unmatched addresses remain warnings.
The simplified 18-district geometry is generated from the Hong Kong Home
Affairs Department public boundary dataset and is versioned under `assets/`.

Reviewed address decisions can be installed without versioning raw addresses.
`scripts/build_private_address_overrides.py` reconciles reviewer fragments with
the private review export and writes only normalized-address SHA-256 hashes plus
controlled district codes to a mode-0600 JSON file. The installer reads that
file from `/home/frappe-user/superset/private/ccd_address_overrides.json` when
present. Direct residential and postal district fields retain higher priority;
reviewed fragments that imply conflicting districts remain unresolved.

## Validation

`scripts/validate_live_metrics.py` reconciles the virtual person dataset with a
separate raw-row-minus-current-group-reduction query. `scripts/benchmark_live_query.py`
times representative Production charts, and `scripts/validate_growth_location.py`
checks growth coverage, district inference, and mapped sex values using aggregate
output only. The test suite checks privacy, filter/global scope, role exclusions,
metadata fields, and synthetic governance edge cases.

`scripts/validate_registration_metadata.py` audits the live Custom Fields and
current-source classifications from a Frappe console. The read-only
`scripts/validate_superset_metadata.py` checks SQLite integrity, dashboard 5,
ownership, viewer scope, filters, global identity charts, and production access
finalization.

For controlled location remediation,
`scripts/export_address_inference_review.py` creates a private mode-0600 CSV of
distinct failed address values and counts. It excludes CCD Master identifiers,
identity-group identifiers, names, contacts, and email fields. Its output must
remain outside Git and must never become a dashboard dataset.

See [OPERATIONS.md](docs/OPERATIONS.md) for backup, rollback, service, and
rebuild procedures.
