.PHONY: up down logs build migrate import-municipalities import-parcels import-sigpac download-ndvi calculate-ndvi aggregate-ndvi classify-parcels shell-db shell-api

# --- Infraestructura ---

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

restart:
	docker compose restart

# --- Base de dades ---

migrate:
	docker compose exec api alembic upgrade head

migrate-down:
	docker compose exec api alembic downgrade -1

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

shell-api:
	docker compose exec api bash

# --- Importació de dades ---

import-municipalities:
	docker compose exec api python scripts/import_municipalities.py

import-parcels:
	docker compose exec api python scripts/import_parcels.py

import-sigpac:
	docker compose exec api python scripts/import_sigpac.py

# --- Processament NDVI ---

download-ndvi:
	docker compose exec api python scripts/download_sentinel2.py

calculate-ndvi:
	docker compose exec api python scripts/calculate_ndvi.py

aggregate-ndvi:
	docker compose exec api python scripts/aggregate_ndvi.py

classify-parcels:
	docker compose exec api python scripts/classify_parcels.py

# --- Pipeline completa ---

pipeline: download-ndvi calculate-ndvi aggregate-ndvi classify-parcels

# --- Setup inicial ---

setup:
	cp -n .env.example .env || true
	docker compose build
	docker compose up -d
	sleep 10
	make migrate
