"""Offline API harness backed by an in-memory SQLite test double."""

import json
import os
import sqlite3
import threading
import uuid as uuidlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg.types.json import Jsonb

os.environ.setdefault("TRACE_ENABLED", "false")
os.environ.setdefault("LOG_TO_FILE", "false")
os.environ.setdefault("ATTACHMENT_SIGNING_KEY", "test-only-signing-key-at-least-32-bytes")

sqlite3.register_adapter(Jsonb, lambda value: json.dumps(value.obj))
sqlite3.register_adapter(datetime, lambda value: value.isoformat())
sqlite3.register_converter("JSON", json.loads)

_ORIGIN = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


U = {
    "priya": _uuid(1),
    "marcus": _uuid(2),
    "dana": _uuid(3),
    "tomas": _uuid(4),
    "alicia": _uuid(101),
    "ben": _uuid(102),
    "ruth": _uuid(103),
}


class _Cursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.rowcount = cursor.rowcount

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        for column in ("created_at", "updated_at", "first_reply_at", "resolved_at", "read_at"):
            value = result.get(column)
            if isinstance(value, str):
                result[column] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    def fetchone(self):
        return self._row(self._cursor.fetchone())


class _Connection:
    def __init__(self, pool):
        self._pool = pool

    def execute(self, sql, params=()):
        if self._pool.fail_queries:
            raise OperationalError("connection refused")
        sql = sql.replace("%s", "?")
        sql = sql.replace(" ILIKE ", " LIKE ")
        sql = sql.replace("TRUE", "1").replace("FALSE", "0")
        params = tuple(str(value) if isinstance(value, uuidlib.UUID) else value for value in params)
        cursor = self._pool._connection.execute(sql, params)
        return _Cursor(cursor)


class SQLitePool:
    """Implements the subset of psycopg_pool used by repositories."""

    def __init__(self):
        self.fail_queries = False
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            ":memory:",
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    @contextmanager
    def connection(self):
        with self._lock:
            try:
                yield _Connection(self)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def execute(self, sql, params=()):
        with self.connection() as connection:
            cursor = connection.execute(sql, params)
            return cursor.fetchall()

    def _create_schema(self):
        self._connection.executescript(
            """
            CREATE TABLE users (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
              role TEXT NOT NULL, password_hash TEXT,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'))
            );
            CREATE TABLE tickets (
              number INTEGER PRIMARY KEY AUTOINCREMENT,
              id TEXT NOT NULL UNIQUE,
              ref TEXT GENERATED ALWAYS AS ('TKT-' || number) STORED UNIQUE,
              employee_id TEXT NOT NULL REFERENCES users(id),
              category TEXT NOT NULL, subject TEXT NOT NULL, description TEXT NOT NULL,
              priority TEXT NOT NULL, status TEXT NOT NULL,
              assignee_id TEXT REFERENCES users(id),
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
              updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
              first_reply_at TEXT, resolved_at TEXT,
              closed_by TEXT REFERENCES users(id), attachment_path TEXT,
              attachment_name TEXT, attachment_size INTEGER
            );
            CREATE TABLE ticket_drafts (
              id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES users(id),
              category TEXT NOT NULL, subject TEXT NOT NULL, description TEXT NOT NULL,
              priority TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
              updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
              attachment_path TEXT, attachment_name TEXT, attachment_size INTEGER
            );
            CREATE TABLE replies (
              id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
              author_id TEXT NOT NULL REFERENCES users(id), author_role TEXT NOT NULL,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'))
            );
            CREATE TABLE notifications (
              id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              ticket_id TEXT REFERENCES tickets(id) ON DELETE CASCADE, ticket_ref TEXT,
              type TEXT NOT NULL, channel TEXT NOT NULL DEFAULT 'in_app', actor_name TEXT,
              payload JSON NOT NULL DEFAULT '{}', message TEXT NOT NULL,
              read INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
              read_at TEXT
            );
            CREATE TABLE attachments (
              path TEXT PRIMARY KEY, data BLOB NOT NULL, content_type TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TRIGGER tickets_updated AFTER UPDATE ON tickets
              WHEN NEW.updated_at = OLD.updated_at BEGIN
                UPDATE tickets SET updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
                WHERE id = NEW.id;
              END;
            CREATE TRIGGER drafts_updated AFTER UPDATE ON ticket_drafts
              WHEN NEW.updated_at = OLD.updated_at BEGIN
                UPDATE ticket_drafts SET updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
                WHERE id = NEW.id;
              END;
            """
        )
        self._connection.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('tickets', 100)")
        self._connection.commit()

    def seed(self):
        tick = 0

        def clock():
            nonlocal tick
            tick += 1
            return (_ORIGIN + timedelta(seconds=tick)).isoformat()

        people = [
            ("Priya Sharma", "priya@acme.com", "employee", U["priya"]),
            ("Marcus Webb", "marcus@acme.com", "employee", U["marcus"]),
            ("Dana Cole", "dana@acme.com", "employee", U["dana"]),
            ("Tomas Nowak", "tomas@acme.com", "employee", U["tomas"]),
            ("Alicia Gomez", "alicia.hr@acme.com", "agent", U["alicia"]),
            ("Ben Osei", "ben.hr@acme.com", "agent", U["ben"]),
            ("Ruth Meyer", "ruth.hr@acme.com", "agent", U["ruth"]),
        ]
        for name, email, role, user_id in people:
            self._connection.execute(
                "INSERT INTO users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, email, role, clock()),
            )

        ticket_rows = [
            (
                U["priya"],
                "Payroll",
                "May payslip missing shift allowance",
                "The May payslip does not include the 12 weekend shift hours I worked.",
                "Medium",
                "Open",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                U["marcus"],
                "Leave",
                "Question about carryover of PTO days",
                "I have 5 pending PTO days. Do they carry over into next quarter or expire?",
                "High",
                "In Progress",
                U["alicia"],
                clock(),
                None,
                "TKT-102/f1ca9.pdf",
                "payslip.pdf",
            ),
            (
                U["dana"],
                "Policy",
                "Policy on remote work equipment",
                "Can I expense a second monitor given the new hybrid work policy applies to me?",
                "Urgent",
                "Resolved",
                U["ben"],
                None,
                clock(),
                None,
                None,
            ),
        ]
        for (
            employee,
            category,
            subject,
            description,
            priority,
            status,
            assignee,
            first_reply,
            resolved,
            attachment_path,
            attachment_name,
        ) in ticket_rows:
            now = clock()
            self._connection.execute(
                """
                INSERT INTO tickets (
                  id, employee_id, category, subject, description, priority, status,
                  assignee_id, first_reply_at, resolved_at, attachment_path, attachment_name,
                  attachment_size, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuidlib.uuid4()),
                    employee,
                    category,
                    subject,
                    description,
                    priority,
                    status,
                    assignee,
                    first_reply,
                    resolved,
                    attachment_path,
                    attachment_name,
                    42 if attachment_path else None,
                    now,
                    now,
                ),
            )
        ticket_id = self._connection.execute(
            "SELECT id FROM tickets WHERE number = 102"
        ).fetchone()["id"]
        self._connection.execute(
            "INSERT INTO replies (id, ticket_id, author_id, author_role, body, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuidlib.uuid4()),
                ticket_id,
                U["alicia"],
                "agent",
                "Looking into the carryover policy now.",
                clock(),
            ),
        )
        self._connection.commit()

    def close(self):
        with self._lock:
            self._connection.close()


@pytest.fixture()
def api(monkeypatch):
    from app import config as app_config
    from app import main as app_main

    fake = SQLitePool()
    fake.seed()
    monkeypatch.setattr(app_config, "get_database", lambda: fake)
    client = TestClient(app_main.app)
    yield SimpleNamespace(client=client, fake=fake, U=U)
    fake.close()


def ticket_payload(employee_id, **over):
    base = {
        "employeeId": employee_id,
        "category": "Payroll",
        "subject": "May payslip missing shift allowance",
        "description": "The May payslip does not include the 12 weekend shift hours I worked.",
        "priority": "High",
    }
    base.update(over)
    return base
