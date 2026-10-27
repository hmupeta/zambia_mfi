#!/usr/bin/env python3
"""
Installer for Phase AD — Docker + CI/CD.
Run from the backend/ directory:   python install_docker.py
"""
import os
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DOCKER_DIR = ROOT / "docker"
GH_DIR = ROOT.parent / ".github" / "workflows"

FILES = []
def add(path, content, mode=None):
    FILES.append((path, content, mode))

# ═════════════════════════════════════════════
# Dockerfile
# ═════════════════════════════════════════════
add(ROOT / "Dockerfile", r'''# ============================================================
# Stage 1: builder — install wheels into a virtualenv
# ============================================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
        libffi-dev \
        gettext \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r requirements.txt && \
    /opt/venv/bin/pip install gunicorn psycopg2-binary redis

# ============================================================
# Stage 2: runtime — slim image with only the virtualenv
# ============================================================
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings \
    DJANGO_ENV=prod

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libjpeg62-turbo \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=appuser:appuser . /app/

# Copy frontend templates (outside backend dir)
COPY --chown=appuser:appuser ../frontend /frontend/

# Prepare dirs and make entrypoint executable
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appuser /app/staticfiles /app/media /app/logs && \
    chmod +x /app/docker/entrypoint.sh /app/docker/healthcheck.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD /app/docker/healthcheck.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
''')

# ═════════════════════════════════════════════
# .dockerignore
# ═════════════════════════════════════════════
add(ROOT / ".dockerignore", r'''# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
htmlcov/
.coverage
.mypy_cache/

# Virtualenv
venv/
.venv/
env/

# Django
db.sqlite3
*.log
logs/
staticfiles/
media/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Env
.env
.env.*
!.env.docker.example

# Git
.git/
.gitignore

# Docker
docker-compose*.yml
Dockerfile
.dockerignore
''')

# ═════════════════════════════════════════════
# docker/entrypoint.sh
# ═════════════════════════════════════════════
add(DOCKER_DIR / "entrypoint.sh", r'''#!/bin/sh
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
''', mode=0o755)

# ═════════════════════════════════════════════
# docker/healthcheck.sh
# ═════════════════════════════════════════════
add(DOCKER_DIR / "healthcheck.sh", r'''#!/bin/sh
# ============================================================
# Container health probe — hits /healthz/
# ============================================================
set -e

curl -fsS http://127.0.0.1:8000/healthz/ > /dev/null \
    || curl -fsS http://127.0.0.1:8000/ > /dev/null \
    || exit 1
exit 0
''', mode=0o755)

# ═════════════════════════════════════════════
# docker/nginx.conf
# ═════════════════════════════════════════════
add(DOCKER_DIR / "nginx.conf", r'''# ============================================================
# Nginx reverse proxy for the Django app
# ============================================================
upstream django_app {
    server web:8000;
}

server {
    listen 80;
    server_name _;

    client_max_body_size 25M;
    keepalive_timeout 65;

    # ---- Static files ----
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # ---- Media files (uploads) ----
    location /media/ {
        alias /app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # ---- Health check bypass ----
    location = /healthz/ {
        proxy_pass http://django_app;
        access_log off;
    }

    # ---- Everything else -> Django ----
    location / {
        proxy_pass http://django_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_read_timeout 90;
    }
}
''')

# ═════════════════════════════════════════════
# docker-compose.yml (production)
# ═════════════════════════════════════════════
add(ROOT / "docker-compose.yml", r'''# ============================================================
# Production stack: Django + Postgres + Redis + Nginx
# ============================================================
services:

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-zambia_mfi}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - backend

  web:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DJANGO_ENV: prod
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      REDIS_URL: redis://redis:6379/0
    volumes:
      - static_files:/app/staticfiles
      - media_files:/app/media
      - ./logs:/app/logs
    expose:
      - "8000"
    networks:
      - backend

  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    depends_on:
      - web
    ports:
      - "80:80"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - static_files:/app/staticfiles:ro
      - media_files:/app/media:ro
    networks:
      - backend

volumes:
  postgres_data:
  redis_data:
  static_files:
  media_files:

networks:
  backend:
    driver: bridge
''')

# ═════════════════════════════════════════════
# docker-compose.dev.yml (dev override)
# ═════════════════════════════════════════════
add(ROOT / "docker-compose.dev.yml", r'''# ============================================================
# Dev override: use with:
#     docker compose -f docker-compose.yml -f docker-compose.dev.yml up
# ============================================================
services:

  web:
    build:
      target: runtime
    command: >
      sh -c "
        python manage.py migrate --noinput &&
        python manage.py runserver 0.0.0.0:8000
      "
    environment:
      DJANGO_ENV: dev
      DEBUG: "True"
    volumes:
      - .:/app
      - ../frontend:/frontend
      - media_files:/app/media
    ports:
      - "8000:8000"

  nginx:
    profiles:
      - donotstart
''')

# ═════════════════════════════════════════════
# .env.docker.example
# ═════════════════════════════════════════════
add(ROOT / ".env.docker.example", r'''# ============================================================
# Copy this to .env and fill in real values
#     cp .env.docker.example .env
# ============================================================

# ---- Django ----
DJANGO_ENV=prod
DEBUG=False
SECRET_KEY=replace-me-with-50-random-chars-USE-openssl-rand-hex-32
ALLOWED_HOSTS=localhost,your-domain.zm,www.your-domain.zm
CSRF_TRUSTED_ORIGINS=https://your-domain.zm,https://www.your-domain.zm

# ---- Database ----
POSTGRES_DB=zambia_mfi
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-me-strong-password
DATABASE_URL=postgres://postgres:change-me-strong-password@db:5432/zambia_mfi

# ---- Redis (cache + broker) ----
REDIS_URL=redis://redis:6379/0

# ---- Superuser (auto-created on first boot) ----
DJANGO_SUPERUSER_EMAIL=admin@your-domain.zm
DJANGO_SUPERUSER_PASSWORD=change-me
DJANGO_SUPERUSER_USERNAME=admin

# ---- JWT ----
JWT_ACCESS_LIFETIME_MINUTES=60
JWT_REFRESH_LIFETIME_DAYS=7

# ---- Email (SMTP) ----
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@your-domain.zm

# ---- SMS (Africa's Talking) ----
SMS_USERNAME=
SMS_API_KEY=
SMS_SENDER_ID=

# ---- WhatsApp (Twilio) ----
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
WHATSAPP_FROM=

# ---- Sentry (optional) ----
SENTRY_DSN=

# ---- Feature flags ----
ENABLE_RATE_LIMITING=True
''')

# ═════════════════════════════════════════════
# Makefile
# ═════════════════════════════════════════════
add(ROOT / "Makefile", r'''# ============================================================
# Common Docker commands
# ============================================================
.PHONY: help build up down logs shell dbshell test migrate fresh clean prod up-dev

help:
	@echo "make build         - Build the Docker image"
	@echo "make up            - Start production stack (db, redis, web, nginx)"
	@echo "make up-dev        - Start dev stack (hot reload, exposed on :8000)"
	@echo "make down          - Stop all containers"
	@echo "make logs          - Tail web container logs"
	@echo "make shell         - Open Django shell inside the container"
	@echo "make dbshell       - Open psql inside the db container"
	@echo "make test          - Run pytest inside the container"
	@echo "make migrate       - Run migrations"
	@echo "make superuser     - Create a superuser interactively"
	@echo "make fresh         - Wipe volumes and rebuild from scratch (DANGEROUS)"
	@echo "make clean         - Stop and remove containers (keep volumes)"

build:
	docker compose build

up:
	docker compose up -d
	@echo "Waiting for app to be ready..."
	@until curl -fsS http://localhost/healthz/ >/dev/null 2>&1; do sleep 1; done
	@echo "Ready: http://localhost/"

up-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web python manage.py shell

dbshell:
	docker compose exec db psql -U postgres -d zambia_mfi

test:
	docker compose exec web python -m pytest -v

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations

superuser:
	docker compose exec web python manage.py createsuperuser

fresh:
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d

clean:
	docker compose down
	docker image prune -f

prod:
	docker compose -f docker-compose.yml up -d --build
''')

# ═════════════════════════════════════════════
# GitHub Actions — Docker build + push
# ═════════════════════════════════════════════
add(GH_DIR / "docker.yml", r'''name: Docker Build & Push

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ./backend
          file: ./backend/Dockerfile
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64
''')

# ═════════════════════════════════════════════
# Write all files
# ═════════════════════════════════════════════
def main():
    print("Installing Docker + CI/CD files...")
    for path, content, *rest in FILES:
        mode = rest[0] if rest else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if mode is not None:
            try:
                os.chmod(path, mode)
            except Exception:
                pass
        try:
            rel = path.relative_to(ROOT.parent)
        except ValueError:
            rel = path
        print(f"  + {rel}")

    print(f"\nDone. {len(FILES)} files written.")
    print()
    print("Next steps:")
    print("  1. cp .env.docker.example .env   (fill in real values)")
    print("  2. docker compose build")
    print("  3. docker compose up -d")
    print("  4. Open http://localhost/")
    print()
    print("For local dev (hot reload):")
    print("  docker compose -f docker-compose.yml -f docker-compose.dev.yml up")


if __name__ == "__main__":
    main()