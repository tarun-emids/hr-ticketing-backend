"""Offline test harness: in-memory fake of the Supabase client.

The repositories use a small, fixed subset of the supabase-py query builder:
select/insert/update/delete chained with eq/is_/ilike/lt/order/limit, then
execute(). This fake implements exactly that surface so endpoint logic can be
tested without a real Supabase project or network access.

Wiring: every repository gets its client through app/deps.py, which resolves
`app.config.get_client()` at call time — so patching app.config.get_client
swaps in the fake for ALL layers at once (controllers -> services -> repos).
"""

import os
import uuid as uuidlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

# Observability: keep the offline suite tracer-free and hermetic (no OTLP
# exporter, no attempted export, no log files written into the repo).
# tests/unit/test_observability.py manages its own tracer providers.
# This must run before app.config is first imported.
os.environ.setdefault("TRACE_ENABLED", "false")
os.environ.setdefault("LOG_TO_FILE", "false")

_orchestrated = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


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


def _fk_error(message: str) -> APIError:
    return APIError({"message": message, "code": "23503"})


class _Result:
    """Mimics the APIResponse envelope (.data attribute)."""

    def __init__(self, data):
        self.data = data


class FakeQueryBuilder:
    def __init__(self, table, op="select"):
        self._table = table
        self._op = op
        self._payload = None
        self._returning = False
        self._filters = []
        self._order = []
        self._limit = None

    def select(self, _cols="*", **kw):
        if self._op in ("insert", "update"):
            self._returning = True
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        self._returning = False
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
        self._returning = False
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def in_(self, col, values):
        # PostgREST vals arrive json-dumped; the fake only ever filters text.
        self._filters.append(("in", col, [str(v) for v in (values or [])]))
        return self

    def lt(self, col, val):
        self._filters.append(("lt", col, val))
        return self

    def order(self, col, desc=False, **kw):
        self._order.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    # -- execution ---------------------------------------------------------

    def _matched(self):
        rows = self._table.rows
        for kind, col, val in self._filters:
            if kind == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif kind == "is":
                rows = [r for r in rows if r.get(col) is None]
            elif kind == "ilike":
                pat = val.replace("%", "").lower()
                rows = [r for r in rows if pat in str(r.get(col) or "").lower()]
            elif kind == "in":
                rows = [r for r in rows if str(r.get(col)) in val]
            elif kind == "lt":
                rows = [r for r in rows if str(r.get(col) or "") < str(val)]
        return rows

    def execute(self):
        t = self._table
        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            data = [t.on_insert(dict(p)) for p in payloads]
        elif self._op == "update":
            rows = self._matched()
            for r in rows:
                r.update(self._payload)
                t.touch(r)
            data = list(rows) if self._returning else []
        elif self._op == "delete":
            doomed = self._matched()
            t.rows = [r for r in t.rows if r not in doomed]
            data = list(doomed) if self._returning else []
        else:
            data = self._matched()
            for col, desc in self._order:
                data = sorted(data, key=lambda r: str(r.get(col) or ""), reverse=desc)
            if self._limit is not None:
                data = data[: self._limit]
        return _Result(data)


class FakeTable:
    def __init__(self, supa, name):
        self.supa = supa
        self.name = name
        self.rows = []

    def select(self, _cols="*", **kw):
        return FakeQueryBuilder(self, "select")

    def insert(self, payload):
        builder = FakeQueryBuilder(self, "insert")
        builder.insert(payload)
        return builder

    def update(self, patch):
        builder = FakeQueryBuilder(self, "update")
        builder.update(patch)
        return builder

    def delete(self):
        return FakeQueryBuilder(self, "delete")

    def on_insert(self, payload):
        now = self.supa.clock()
        if self.name == "users":
            row = {
                **payload,
                "id": payload.get("id", _uuid(uuidlib.uuid4().int % 10**12)),
                "created_at": now,
            }
            self.rows.append(row)
            return row
        if self.name == "tickets":
            employee = payload.get("employee_id")
            if not any(r["id"] == employee for r in self.supa.users.rows):
                raise _fk_error(f"insert violates foreign key on employee_id {employee}")
            num = self.supa.next_ticket_number
            self.supa.next_ticket_number += 1
            row = {
                "id": str(uuidlib.uuid4()),
                "number": num,
                "ref": f"TKT-{num}",
                "assignee_id": None,
                "first_reply_at": None,
                "resolved_at": None,
                "closed_by": None,
                "attachment_path": None,
                "attachment_name": None,
                "attachment_size": None,
                **payload,
                "created_at": now,
                "updated_at": now,
            }
            self.rows.append(row)
            return row
        if self.name == "replies":
            if not any(r["id"] == payload.get("ticket_id") for r in self.supa.tickets.rows):
                raise _fk_error("insert violates foreign key on replies.ticket_id")
            if not any(r["id"] == payload.get("author_id") for r in self.supa.users.rows):
                raise _fk_error("insert violates foreign key on replies.author_id")
            row = {**payload, "id": str(uuidlib.uuid4()), "created_at": now}
            self.rows.append(row)
            return row
        if self.name == "notifications":
            row = {
                "id": str(uuidlib.uuid4()),
                "ticket_id": None,
                "ticket_ref": None,
                "actor_name": None,
                "payload": {},
                "channel": "in_app",
                "read_at": None,
                **payload,
            }
            self.rows.append(row)
            return row
        if self.name == "ticket_drafts":
            row = {
                **payload,
                "id": str(uuidlib.uuid4()),
                "created_at": now,
                "updated_at": now,
                "attachment_path": None,
                "attachment_name": None,
                "attachment_size": None,
            }
            self.rows.append(row)
            return row
        if self.name == "kb_documents":
            row = {
                **payload,
                "id": str(uuidlib.uuid4()),
                "created_at": now,
                "updated_at": now,
            }
            self.rows.append(row)
            return row
        row = {**payload, "id": str(uuidlib.uuid4())}
        self.rows.append(row)
        return row

    def touch(self, row):
        if self.name == "tickets":
            row["updated_at"] = self.supa.clock()


class FakeStorage:
    def __init__(self, supa, bucket):
        self.supa = supa
        self.bucket = bucket

    def upload(self, path, data, opts=None):
        if self.supa.fail_uploads:
            raise RuntimeError("storage down")
        self.supa.storage_files[(self.bucket, path)] = bytes(data)

    def create_signed_url(self, path, ttl, options=None):
        self.supa.last_signed_ttl = ttl
        self.supa.last_signed_options = options
        url = f"https://fake.supabase.co/storage/v1/object/sign/{self.bucket}/{path}?token=x"
        return {"signedURL": url}


class FakeStorageClient:
    def __init__(self, supa):
        self.supa = supa

    def from_(self, bucket):
        # from_ is technically not a method on the storage client in supabase-py
        # (it's a reserved-code workaround name the backend uses), emulate it.
        return FakeStorage(self.supa, bucket)


class FakeSupabase:
    """Fake supabase.Client — supports .table(name) and .storage."""

    def __init__(self):
        self.users = FakeTable(self, "users")
        self.tickets = FakeTable(self, "tickets")
        self.replies = FakeTable(self, "replies")
        self.notifications = FakeTable(self, "notifications")
        self.ticket_drafts = FakeTable(self, "ticket_drafts")
        self.kb_documents = FakeTable(self, "kb_documents")
        self.storage = FakeStorageClient(self)
        self.storage_files = {}
        self.fail_uploads = False
        self.last_signed_ttl = None
        self.last_signed_options = None
        self._tick = 0
        self.next_ticket_number = 101

    def table(self, name):
        def tables():
            return {
                "users": self.users,
                "tickets": self.tickets,
                "replies": self.replies,
                "notifications": self.notifications,
                "ticket_drafts": self.ticket_drafts,
                "kb_documents": self.kb_documents,
            }

        return tables()[name]

    def seed_kb(self):
        """3 employee + 2 HR policy documents; used by the /kb tests."""
        return seed_kb_rows(self)

    def clock(self):
        self._tick += 1
        return (_orchestrated + timedelta(seconds=self._tick)).isoformat()

    def seed_users(self):
        people = [
            ("Priya Sharma", "priya@acme.com", "employee", U["priya"]),
            ("Marcus Webb", "marcus@acme.com", "employee", U["marcus"]),
            ("Dana Cole", "dana@acme.com", "employee", U["dana"]),
            ("Tomas Nowak", "tomas@acme.com", "employee", U["tomas"]),
            ("Alicia Gomez", "alicia.hr@acme.com", "agent", U["alicia"]),
            ("Ben Osei", "ben.hr@acme.com", "agent", U["ben"]),
            ("Ruth Meyer", "ruth.hr@acme.com", "agent", U["ruth"]),
        ]
        for name, email, role, uid in people:
            self.users.rows.append(
                {
                    "id": uid,
                    "name": name,
                    "email": email,
                    "role": role,
                    "created_at": self.clock(),
                }
            )

    def seed_tickets(self):
        """Three demo tickets mirroring src/data/store.js shape. Created via the
        fake itself so ref numbering/id sequence behaves like the real identity."""
        t101 = {
            "employee_id": U["priya"],
            "category": "Payroll",
            "subject": "May payslip missing shift allowance",
            "description": "The May payslip does not include the 12 weekend shift hours I worked.",
            "priority": "Medium",
            "status": "Open",
        }
        t102 = {
            "employee_id": U["marcus"],
            "category": "Leave",
            "subject": "Question about carryover of PTO days",
            "description": "I have 5 pending PTO days. Do they carry over into next quarter or expire?",
            "priority": "High",
            "status": "In Progress",
            "assignee_id": U["alicia"],
            "first_reply_at": self.clock(),
            "attachment_path": "TKT-102/f1ca9.pdf",
            "attachment_name": "payslip.pdf",
            "attachment_size": 42,
        }
        t103 = {
            "employee_id": U["dana"],
            "category": "Policy",
            "subject": "Policy on remote work equipment",
            "description": "Can I expense a second monitor given the new hybrid work policy applies to me?",
            "priority": "Urgent",
            "status": "Resolved",
            "assignee_id": U["ben"],
            "resolved_at": self.clock(),
        }
        for spec in (t101, t102, t103):
            self.tickets.on_insert(spec)
        # one agent reply on TKT-102 (needs the ticket row first)
        self.replies.on_insert(
            {
                "ticket_id": self.tickets.rows[1]["id"],
                "author_id": U["alicia"],
                "author_role": "agent",
                "body": "Looking into the carryover policy now.",
            }
        )


@pytest.fixture()
def api(monkeypatch):
    """TestClient + FakeSupabase wired in place of the real Supabase client."""
    from app import config as app_config
    from app import main as app_main

    fake = FakeSupabase()
    fake.seed_users()
    fake.seed_tickets()
    fake.seed_kb()

    def wire(module):
        if hasattr(module, "get_client"):
            monkeypatch.setattr(module, "get_client", lambda: fake)
        if hasattr(module, "db"):
            monkeypatch.setattr(module, "db", lambda: fake.table("tickets"))

    # Single point of truth: every repository resolves its client through
    # app.deps -> app.config.get_client() at request time.
    wire(app_config)

    client = TestClient(app_main.app)
    yield SimpleNamespace(client=client, fake=fake, U=U)


# Shared, valid creation payload for POST /api/tickets
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


def kb_row(slug, ref, title, audience, *, category="General", keywords="",
           summary="", search_text="", updated_at=None):
    """A kb_documents row shaped exactly like the schema (section 9)."""
    return {
        "id": str(uuidlib.uuid4()),
        "slug": slug,
        "ref": ref,
        "title": title,
        "category": category,
        "audience": audience,
        "summary": summary or f"{title} policy summary.",
        "keywords": keywords,
        "search_text": search_text or f"{title} {summary or ''} {keywords}".lower(),
        "file_path": f"pdf/{ref.lower()}-{slug}.pdf",
        "file_size": 12345,
        "page_count": 7,
        "version": "v1.0",
        "effective_date": "2026-04-01",
        "created_at": _orchestrated.isoformat(),
        "updated_at": updated_at or _orchestrated.isoformat(),
    }


_SEED_KB = [
    dict(slug="leave-and-time-off-policy", ref="KB-E-01",
         title="Leave and Time Off Policy", category="Leave",
         audience="employee",
         keywords="leave, pto, vacation, sick, carryover",
         summary="How time off accrues, carries over and gets approved."),
    dict(slug="hybrid-work-policy", ref="KB-E-02",
         title="Hybrid Work Policy", category="Workplace",
         audience="employee",
         keywords="hybrid, remote, office, equipment",
         summary="Weeks per month on site and what the office provides."),
    dict(slug="attendance-working-hours-policy", ref="KB-E-03",
         title="Attendance and Working Hours Policy", category="Workplace",
         audience="employee",
         keywords="attendance, working hours, shifts",
         summary="Core hours, shift expectations and attendance recording."),
    dict(slug="payroll-processing-sop", ref="KB-HR-01",
         title="Payroll Processing SOP", category="Payroll",
         audience="hr",
         keywords="payroll, run, cutoff, anomaly",
         summary="The monthly payroll cycle runbook, cutoffs and anomaly flow."),
    dict(slug="exit-process-sop", ref="KB-HR-02",
         title="Exit Process SOP", category="Offboarding", audience="hr",
         keywords="exit, offboarding, clearance, fnf",
         summary="Notice, clearance and final-settlement steps for leavers."),
]


def seed_kb_rows(fake):
    """Routine used by the fixture (and importable by other test modules):
    3 employee + 2 HR documents in the fake store + PDF bytes for the viewer."""
    rows = [kb_row(**spec) for spec in _SEED_KB]
    fake.kb_documents.rows.extend(rows)
    for row in rows:
        fake.storage_files[("knowledge-base", row["file_path"])] = b"%PDF-1.4 fake-pdf-bytes"
    return rows
