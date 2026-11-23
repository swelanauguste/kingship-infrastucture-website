import os
import sys
import time

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cf.settings")
import django
django.setup()
from django.db import connection
from django.core.cache import cache

for attempt in range(30):
    try:
        connection.ensure_connection()
        cache.set("startup-check", "ok", 30)
        if cache.get("startup-check") != "ok":
            raise RuntimeError("Cache unavailable")
        print("Shared database and cache are ready.", flush=True)
        break
    except Exception:
        connection.close()
        if attempt == 29:
            raise RuntimeError("Shared services unavailable after 30 attempts.") from None
        print("Waiting for shared PostgreSQL and Redis...", flush=True)
        time.sleep(2)
