.PHONY: up up-db down logs restart-api test test-fast lint shell create-user seed migrate e2e e2e-install fe-install fe-build fe-dev

up:
	docker compose up -d --build

up-db:
	docker compose up -d db

down:
	docker compose down

logs:
	docker compose logs -f api

# Restart just the api container. With --reload in compose this is now rare,
# but useful when you change pyproject.toml (new deps require image rebuild)
# or compose-level config.
restart-api:
	docker compose restart api

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

# Idempotent dev seed: create t@t.com / pw if missing.
seed:
	docker compose run --rm api python -m backend.cli seed-dev

# ---------- Frontend ----------
fe-install:
	cd frontend && npm install

fe-build:
	cd frontend && npm run build

fe-dev:
	cd frontend && npm run dev

# ---------- E2E (Playwright) ----------
# One-shot install of @playwright/test + browser. Safe to re-run.
e2e-install:
	cd frontend && npm install --save-dev @playwright/test && npx playwright install chromium

# Run the happy-path E2E. Assumes `make up` is running (api on :8000) and that
# a default seed user (t@t.com/pw) exists via `make seed`.
e2e:
	cd frontend && npx playwright test --config=../playwright.config.ts
