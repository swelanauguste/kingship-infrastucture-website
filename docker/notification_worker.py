import logging
import os
import signal
import sys
from threading import Event

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cf.settings")
import django
django.setup()
from django.core.management import call_command
from django.db import close_old_connections

logging.basicConfig(level=logging.INFO)
stop = Event()
for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, lambda *_: stop.set())

while not stop.is_set():
    close_old_connections()
    try:
        call_command("send_notifications")
    except Exception:
        logging.exception("Notification run failed; retrying in five minutes.")
    stop.wait(300)
