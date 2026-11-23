#!/bin/sh
set -eu
case "${1:-}" in
  init)
    python /app/docker/wait_for_services.py
    python manage.py migrate --noinput
    exec python manage.py collectstatic --noinput
    ;;
  notifications)
    exec python /app/docker/notification_worker.py
    ;;
  *)
    exec "$@"
    ;;
esac
