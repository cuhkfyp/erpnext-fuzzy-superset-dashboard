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

# Deck.gl runs through MapLibre and uses only public basemap tiles. Client data
# remains in the polygon layer returned by Superset and is never sent to the
# tile provider.
DEFAULT_MAP_RENDERER = "maplibre"
DECKGL_BASE_MAP = [
    ["tile://https://tile.openstreetmap.org/{z}/{x}/{y}.png", "OpenStreetMap"],
]

_ccd_csp = TALISMAN_CONFIG.setdefault("content_security_policy", {})
for _ccd_directive, _ccd_values in {
    "connect-src": ["'self'", "https://tile.openstreetmap.org"],
    "img-src": ["'self'", "data:", "blob:", "https://tile.openstreetmap.org"],
}.items():
    _ccd_existing = _ccd_csp.setdefault(_ccd_directive, [])
    for _ccd_value in _ccd_values:
        if _ccd_value not in _ccd_existing:
            _ccd_existing.append(_ccd_value)
