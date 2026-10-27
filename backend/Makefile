# ============================================================
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
