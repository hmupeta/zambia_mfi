#!/bin/sh
# ============================================================
# Container entrypoint — waits for DB, migrates, collects static
# ============================================================
set -e

echo "==> Waiting for PostgreSQL..."
until python -c "
import os, sys, psycopg2
try:
    psycopg2.connect(
        dbname=os.environ.get('POSTGRES_DB', 'zambia_mfi'),
        user=os.environ.get('POSTGRES_USER', 'postgres'),
        password=os.environ.get('POSTGRES_PASSWORD', ''),
        host=os.environ.get('POSTGRES_HOST', 'db'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
    )
except Exception:
    sys.exit(1)
sys.exit(0)
" 2>/dev/null; do
    sleep 1
done
echo "==> PostgreSQL is up."

echo "==> Applying migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Ensuring superuser exists..."
    python manage.py createsuperuser --noinput || true
fi

echo "==> Ready. Starting: $@"
exec "$@"
