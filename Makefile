.PHONY: up up-db down logs test test-fast lint shell create-user seed migrate

up:
	docker compose up -d --build

up-db:
	docker compose up -d db

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	docker compose run --rm api pytest -v

test-fast:
	docker compose run --rm api pytest -x --ff -q

lint:
	docker compose run --rm api ruff check backend

migrate:
	docker compose run --rm api alembic upgrade head

shell:
	docker compose exec api bash

create-user:
	@read -p "name: " name; \
	 read -p "email: " email; \
	 read -sp "password: " password; \
	 docker compose run --rm api python -m backend.cli create-user --name "$$name" --email "$$email" --password "$$password"

seed:
	docker compose run --rm api python -m backend.cli seed
