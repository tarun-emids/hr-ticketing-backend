"""Shared, parameterized PostgreSQL execution for repositories."""

import re
import uuid
from datetime import datetime
from typing import Any

import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app.observability import db_span
from app.resilience import CircuitOpenError, db_breaker

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
UUID_COLUMNS = frozenset(
    {"id", "employee_id", "assignee_id", "closed_by", "ticket_id", "author_id", "recipient_id"}
)
TIMESTAMP_COLUMNS = frozenset(
    {"created_at", "updated_at", "first_reply_at", "resolved_at", "read_at"}
)


def as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _adapt_column_value(column: str, value: Any) -> Any:
    if column in UUID_COLUMNS and isinstance(value, str) and UUID_RE.fullmatch(value):
        return as_uuid(value)
    if column in TIMESTAMP_COLUMNS and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _db_failure(exc: BaseException) -> bool:
    """Only connection/resource failures indicate that PostgreSQL is down."""
    if isinstance(exc, PoolTimeout):
        return True
    if isinstance(exc, psycopg.Error):
        state = exc.sqlstate or ""
        if state.startswith(("23", "22", "42")):
            return False
        return state.startswith(("08", "28", "53", "57")) or isinstance(
            exc, (psycopg.OperationalError, psycopg.InterfaceError)
        )
    return False


def run(
    database: ConnectionPool,
    sql: str,
    params: tuple | list = (),
    *,
    fetch: str = "all",
    table: str = "query",
) -> Any:
    """Execute one SQL statement through the shared connection pool and breaker."""
    operation = sql.lstrip().split(None, 1)[0].lower()

    def execute():
        with database.connection() as connection:
            cursor = connection.execute(sql, params)
            if fetch == "all":
                return cursor.fetchall()
            if fetch == "one":
                return cursor.fetchone()
            return cursor.rowcount

    try:
        with db_span(
            f"db.postgresql.{table}.{operation}",
            {"db.system": "postgresql", "db.operation": operation, "db.sql.table": table},
        ):
            return db_breaker.call(execute, is_failure=_db_failure)
    except CircuitOpenError:
        raise HTTPException(
            status_code=503,
            detail="Database is temporarily unavailable — try again shortly.",
        ) from None
    except (psycopg.Error, PoolTimeout) as exc:
        state = getattr(exc, "sqlstate", None) or ""
        if state.startswith(("23", "22")):
            raise HTTPException(
                status_code=400,
                detail="Database rejected the write.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="Database operation failed — try again shortly.",
        ) from exc


def rows_of(database: ConnectionPool, sql: str, params: tuple | list = (), *, table: str) -> list:
    return run(database, sql, params, table=table)


def first_of(database: ConnectionPool, sql: str, params: tuple | list = (), *, table: str):
    return run(database, sql, params, fetch="one", table=table)


def insert_row(
    database: ConnectionPool,
    table: str,
    row: dict,
    *,
    json_columns: tuple[str, ...] = (),
) -> dict:
    row = dict(row)
    row.setdefault("id", str(uuid.uuid4()))
    columns = tuple(row)
    if not IDENTIFIER_RE.fullmatch(table) or any(
        not IDENTIFIER_RE.fullmatch(column) for column in columns
    ):
        raise ValueError("Invalid SQL identifier")
    values = tuple(
        Jsonb(row[column]) if column in json_columns else _adapt_column_value(column, row[column])
        for column in columns
    )
    placeholders = ", ".join(["%s"] * len(columns))
    names = ", ".join(columns)
    return first_of(
        database,
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) RETURNING *",
        values,
        table=table,
    )


def insert_many_rows(
    database: ConnectionPool,
    table: str,
    rows: list[dict],
    *,
    json_columns: tuple[str, ...] = (),
) -> list[dict]:
    if not rows:
        return []
    prepared = [dict(row) for row in rows]
    for row in prepared:
        row.setdefault("id", str(uuid.uuid4()))
    columns = tuple(prepared[0])
    if not IDENTIFIER_RE.fullmatch(table) or any(
        not IDENTIFIER_RE.fullmatch(column) for column in columns
    ):
        raise ValueError("Invalid SQL identifier")
    values_list = []
    for row in prepared:
        if tuple(row) != columns:
            raise ValueError("Bulk insert rows must have identical columns in identical order")
        values_list.append(
            tuple(
                Jsonb(row[column])
                if column in json_columns
                else _adapt_column_value(column, row[column])
                for column in columns
            )
        )
    row_placeholders = f"({', '.join(['%s'] * len(columns))})"
    values_placeholders = ", ".join([row_placeholders] * len(values_list))
    flat_values = tuple(value for row_values in values_list for value in row_values)
    names = ", ".join(columns)
    return rows_of(
        database,
        f"INSERT INTO {table} ({names}) VALUES {values_placeholders} RETURNING id",
        flat_values,
        table=table,
    )


def update_row(database: ConnectionPool, table: str, row_id: str, patch: dict) -> None:
    if not patch:
        return
    columns = tuple(patch)
    if not IDENTIFIER_RE.fullmatch(table) or any(
        not IDENTIFIER_RE.fullmatch(column) for column in columns
    ):
        raise ValueError("Invalid SQL identifier")
    assignments = ", ".join(f"{column} = %s" for column in columns)
    params = tuple(_adapt_column_value(column, value) for column, value in patch.items()) + (
        as_uuid(row_id),
    )
    run(
        database,
        f"UPDATE {table} SET {assignments} WHERE id = %s",
        params,
        fetch="none",
        table=table,
    )
