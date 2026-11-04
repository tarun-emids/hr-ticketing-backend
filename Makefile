.PHONY: up down migrate migrate-stamp migrate-revision

up:
	docker compose up --build --detach

down:
	docker compose down

# Alembic schema migrations (see README: "PostgreSQL setup — Schema
# migrations (Alembic)"). `make migrate` runs Alembic inside
# the backend container, so it always talks to the db service the backend
# itself uses. First-time setup for a database that already had schema.sql:
#   make migrate-stamp   (declare the current schema as past revision 0001)
# A fresh (empty) database instead starts with:
#   make migrate         (applies 0001 + everything after)
migrate:
	docker compose exec backend alembic upgrade head

migrate-stamp:
	docker compose exec backend alembic stamp head

migrate-revision: m ?= unnamed-revision
migrate-revision:
	docker compose exec -T backend alembic revision -m "$(m)"
