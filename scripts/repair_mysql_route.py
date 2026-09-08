#!/usr/bin/env python3
"""Safely restore Superset's MariaDB connection to the stable ERPNext alias."""

from __future__ import annotations

import argparse
import os

os.environ.setdefault(
    "SUPERSET_CONFIG_PATH", "/home/frappe-user/superset/superset_config.py"
)
os.environ.setdefault("FLASK_APP", "superset")

import MySQLdb
from sqlalchemy.engine import make_url
from superset.app import create_app
from superset.extensions import db


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-id", type=int, default=1)
    parser.add_argument("--host", default="erpnext_db")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


args = arguments()
app = create_app()
with app.app_context():
    from superset.models.core import Database

    database = db.session.get(Database, args.database_id)
    if database is None:
        raise RuntimeError(f"Superset database {args.database_id} does not exist")
    current_url = make_url(database.sqlalchemy_uri_decrypted)
    if not current_url.drivername.startswith("mysql"):
        raise RuntimeError(
            f"Refusing to change non-MySQL database {args.database_id}: "
            f"{current_url.drivername}"
        )
    if not current_url.database:
        raise RuntimeError("The configured MySQL database name is empty")

    target_url = current_url.set(host=args.host)
    connection = MySQLdb.connect(
        host=args.host,
        port=target_url.port or 3306,
        user=target_url.username,
        passwd=target_url.password or "",
        db=target_url.database,
        connect_timeout=5,
    )
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("MariaDB validation query returned an unexpected result")
    finally:
        connection.close()

    changed = current_url.host != args.host
    if args.apply and changed:
        database.set_sqlalchemy_uri(target_url.render_as_string(hide_password=False))
        db.session.commit()

    print(
        {
            "database_id": database.id,
            "database_name": database.database_name,
            "previous_host": current_url.host,
            "target_host": args.host,
            "target_port": target_url.port or 3306,
            "connectivity": "ok",
            "changed": bool(args.apply and changed),
            "mode": "apply" if args.apply else "check-only",
        }
    )
