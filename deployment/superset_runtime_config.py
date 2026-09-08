"""Non-secret block installed into the existing Superset configuration."""

import logging


# Live SQL is deliberate for this release. No active Redis or in-process data
# cache may make the dashboard appear fresher than MariaDB.
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}

# The managed Gunicorn process is a production runtime, not the prior Flask
# debugger. Keep operational logs useful without exposing debug tracebacks.
DEBUG = False
FLASK_DEBUG = False
SHOW_STACKTRACE = False
LOG_LEVEL = logging.INFO
