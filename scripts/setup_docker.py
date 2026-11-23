"""Provision this app's dev database without changing shared service settings."""
import os
from pathlib import Path
import re
import secrets
import subprocess


root = Path(__file__).resolve().parent.parent
env_path = root / ".env.docker"
if not env_path.exists():
    template = (root / ".env.docker.example").read_text()
    template = template.replace("replace-with-a-long-random-secret", secrets.token_urlsafe(64))
    template = template.replace("replace-with-a-unique-database-password", secrets.token_urlsafe(40))
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(template)
    print("Created private .env.docker with generated app credentials.")

values = {}
for line in env_path.read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
for key in ("DB_NAME", "DB_USER"):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", values.get(key, "")):
        raise SystemExit(f"Set {key} to a lowercase PostgreSQL identifier in .env.docker.")
if not values.get("DB_PASSWORD") or values["DB_PASSWORD"].startswith("replace-"):
    raise SystemExit("Set a unique DB_PASSWORD in .env.docker.")


def literal(value):
    return "'" + value.replace("'", "''") + "'"


role = literal(values["DB_USER"])
database = literal(values["DB_NAME"])
password = literal(values["DB_PASSWORD"])
sql = rf"""
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', {role}, {password})
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role})
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', {database}, {role})
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = {database})
\gexec
"""
container = os.environ.get("SHARED_POSTGRES_CONTAINER", "shared-services-dev-postgres-1")
result = subprocess.run(["docker", "exec", "-i", container, "sh", "-c",
    'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'],
    input=sql, text=True, capture_output=True)
if result.returncode:
    # psql errors may include a SQL statement: never print application credentials.
    detail = result.stderr.replace(values["DB_PASSWORD"], "[redacted]")
    raise SystemExit(f"Database setup failed. Start the shared dev services and retry.\n{detail}")
print("Application role and database are ready; existing databases and credentials preserved.")
print("Start with: docker compose --env-file .env.docker up -d --build --wait")
