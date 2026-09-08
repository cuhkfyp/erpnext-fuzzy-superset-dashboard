"""Future isolated cache profile. Do not import in the current release."""

import os


_redis_url = os.environ["CCD_SUPERSET_REDIS_URL"]
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "ccd-superset-data:",
}

