# Operations and rollback

## Scope boundaries

The runtime scripts manage only `/home/frappe-user/superset`,
`hksr-superset.service`, the `hksr-mariadb-proxy` units, and
`/usr/local/sbin/hksr-superset-restart`. They do not restart or reconfigure
ERPNext, n8n, or Redis containers. Do not enable the future Redis Compose
profile in this release.

## MariaDB routes

The canonical Superset database host is `erpnext_db:3306`. A systemd
socket-activated proxy listens only on `127.0.0.1:3306` and forwards to that
same alias, retaining compatibility with legacy local clients without exposing
MariaDB publicly. Use `scripts/repair_mysql_route.py` first in check-only mode,
then with `--apply`, to replace an accidental loopback host in Superset metadata.
The script tests `SELECT 1` before committing and never prints the URI or
credentials.

Validate both paths with a TCP probe and execute the representative chart-data
validator after the repair. Enabling or restarting the proxy must not restart
or recreate the MariaDB, ERPNext, n8n, or Redis containers.

## Metadata backup

Stop no service for the initial online copy; SQLite's integrity check on the
decompressed private copy is the acceptance gate. Store the gzip and SHA-256
sidecar under a mode-0700 private directory and enforce mode 0600 on the gzip.
Never place the database or backup in this repository.

## Dashboard rebuild

Copy the live metadata database to a disposable path, run the installer twice,
check `PRAGMA integrity_check`, then start a disposable Superset instance on a
non-production port with a temporary config pointing to the copy. Confirm the
four datasets and 24 charts before running the same installer against live
metadata. Stable UUIDs make this an upsert, not a duplicate import.

## Runtime rollback

`hksr-superset-restart` performs configuration import preflight before stopping
anything. During cutover it records and terminates only the exact legacy
`superset run -h 0.0.0.0 -p 8088` PID or the known ten-worker Gevent daemon
signature previously launched by `run.sh`. If managed startup or HTTPS health
fails, it restores the detected prior command. Configuration backups are stored
outside the repository under `private_security/superset-config-backups`.

The managed service uses the renewed chain at
`/home/frappe-user/superset/certs/fullchain.pem` and checks that it remains valid
for at least 24 hours before cutover. Do not launch `run.sh` in parallel with
the service: ten Gevent workers are unsupported with the SQLite metadata backend
and can create a query stampede when a dashboard opens.

For a metadata rollback, stop only `hksr-superset.service`, retain the failed
database for investigation, decompress the verified private backup to a new
file, atomically replace `superset.db`, preserve ownership/mode, and start the
service. Recheck `/health` and the dashboard-5 hash.

## Access checks

`CCD Dashboard Viewer` receives only four dynamic `datasource_access` entries
and one dashboard-role link. It has no `database_access`, `schema_access`,
`all_datasource_access`, SQL Lab menu/action, CSV/export, or drill permission.
Superset Admin users remain unrestricted. ERPNext roles are unrelated.
