# fix_migration.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

with connection.cursor() as c:
    c.execute("DELETE FROM django_migrations WHERE app='notifications'")
    print(f"Deleted {c.rowcount} stale migration records for 'notifications'.")