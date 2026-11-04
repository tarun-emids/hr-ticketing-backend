"""Alembic environment for the HR Desk PostgreSQL schema.
Workflow reference: README — "PostgreSQL setup — Schema migrations (Alembic)".

The backend talks to PostgreSQL through psycopg3 with hand-written SQL —
there are no ORM models to autogenerate from, so every revision is written
by hand and validated against a database before being committed
(`make migrate-revision m="..."` creates the empty file; you fill it in and
run `make migrate`).

URL resolution (first hit wins):
  1. ``alembic -x url=<URL>`` — explicit override (scratch databases),
  2. ``DATABASE_URL`` in the environment — what compose injects into the
     backend container, where ``make migrate`` runs Alembic,
  3. ``DATABASE_URL`` loaded from the backend's own .env file (host runs),
  4. the compose-local default (hrdesk on localhost).

The resolved URL is rewritten to SQLAlchemy's psycopg3 dialect
(``postgresql://...`` -> ``postgresql+psycopg://...``) so Alembic speaks
exactly the driver the application itself uses.
"""

import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

config = context.config

# No ORM models exist (psycopg repositories, raw SQL everywhere) — metadata
# would only enable `alembic revision --autogenerate`, which we must NOT
# hand to a schema this hand-tuned.
target_metadata = None


def _resolve_url() -> str:
    custom = context.get_x_argument(as_dictionary=True).get("url", "")
    if custom:
        return custom
    # Same precedence semantics as app/config.py: real environment wins over
    # the .env file, and the .env file only fills in what is missing.
    load_dotenv(BACKEND_DIR / ".env")
    return (
        os.environ.get("DATABASE_URL")
        or "postgresql://hrdesk:local-development-only@localhost:5432/hrdesk"
    )


def _to_psycopg3_dialect(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url  # already dialect-qualified


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=_to_psycopg3_dialect(_resolve_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        {"sqlalchemy.url": _to_psycopg3_dialect(_resolve_url())},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
