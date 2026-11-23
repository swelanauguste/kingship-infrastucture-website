FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=cf.settings

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt \
    && groupadd --gid 10001 ministry \
    && useradd --uid 10001 --gid ministry --no-create-home ministry \
    && mkdir -p /srv/static /srv/media /srv/emails \
    && chown -R ministry:ministry /srv

COPY --chown=ministry:ministry app/ /app/
COPY --chown=ministry:ministry docker/ /app/docker/
USER ministry
ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "cf.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=60", "--access-logfile=-", "--error-logfile=-"]
