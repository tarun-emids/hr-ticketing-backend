"""Repository helper tests for PostgreSQL identifiers and SQL error mapping."""

import uuid as uuidlib
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from psycopg.errors import ForeignKeyViolation, InvalidPassword, SyntaxError

from app.repositories.base import _db_failure, run
from app.repositories.ticket_repository import ticket_ref


class _BrokenConnection:
    def __init__(self, error):
        self.error = error

    def execute(self, _sql, _params):
        raise self.error


class _BrokenPool:
    def __init__(self, error):
        self.connection_instance = _BrokenConnection(error)

    @contextmanager
    def connection(self):
        yield self.connection_instance


def test_ticket_ref_uuid_routes_to_id_column():
    uid = str(uuidlib.uuid4())
    assert ticket_ref(uid) == ("id", uid)


def test_ticket_ref_numeric_becomes_tkt_prefix():
    assert ticket_ref("123") == ("ref", "TKT-123")


def test_ticket_ref_explicit_ref_stays():
    assert ticket_ref("TKT-123") == ("ref", "TKT-123")


def test_ticket_ref_garbage_gets_prefixed():
    assert ticket_ref("abc!") == ("ref", "TKT-abc!")


def test_constraint_error_maps_to_400_without_counting_as_outage():
    error = ForeignKeyViolation("foreign key violated")
    assert not _db_failure(error)
    with pytest.raises(HTTPException) as exc:
        run(_BrokenPool(error), "INSERT INTO tickets (employee_id) VALUES (%s)", ("bad",))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Database rejected the write."


def test_database_outage_maps_to_502_and_counts():
    from psycopg import OperationalError

    error = OperationalError("connection refused")
    assert _db_failure(error)
    with pytest.raises(HTTPException) as exc:
        run(_BrokenPool(error), "SELECT * FROM users", table="users")
    assert exc.value.status_code == 502


def test_sql_syntax_error_does_not_trip_the_database_breaker():
    error = SyntaxError("invalid SQL")
    assert not _db_failure(error)


def test_invalid_database_credentials_do_not_trip_the_breaker():
    assert not _db_failure(InvalidPassword("invalid credentials"))
