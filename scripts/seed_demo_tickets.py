"""Seed a believable demo dataset: N tickets spread over the REAL employees
present in this database — varied categories/priorities/statuses, dates
spread over ~21 days, agent pickup replies on assigned tickets — so the
paginated inbox has real pages to show a reviewer.

Inspect-then-fill rule: employees and agents are read from public.users and
tickets are distributed across the accounts that actually exist. Demo rows
are recognizable by the "(DEMO) " subject marker.

Idempotent: subjects are deterministic (template + batch suffix), and rows
whose subject already exists are skipped. Use --reset to delete all demo
rows first (replies/notifications/feedback cascade via FKs).

    python scripts/seed_demo_tickets.py             # fill to 30 demo rows
    python scripts/seed_demo_tickets.py --count 60  # ~3 pages at 25/page
    python scripts/seed_demo_tickets.py --reset     # start over
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

MARKER = "(DEMO) "
ACTIVE = ("Open", "In Progress", "Waiting on Employee")

# (category, subject, description, priority) — deterministic template pool.
# Long enough for schema CHECKs (subject >= 5 chars, description >= 20).
_TEMPLATES = [
    (
        "Payroll",
        "Question about overtime rate on my payslip",
        "The overtime rate on this month's payslip looks lower than my band.",
    ),
    (
        "Leave",
        "Carryover rules for unused PTO days next quarter",
        "I have five pending PTO days. Do they carry over or expire?",
    ),
    (
        "Benefits",
        "Dental plan coverage for partial orthodontics",
        "Does the new dental plan cover partial orthodontic treatment?",
    ),
    (
        "Onboarding",
        "Missing hardware in my onboarding checklist",
        "My onboarding checklist did not include a second monitor request.",
    ),
    (
        "Policy",
        "Clarification on the hybrid work policy clause",
        "The hybrid work policy clause on anchor days is unclear to me.",
    ),
    (
        "Payroll",
        "Missing transport allowance in April payslip",
        "April's payslip seems to be missing the transport allowance line.",
    ),
    (
        "Leave",
        "How many leaves carry an advance notice period",
        "Which leave types need advance notice and how much in advance?",
    ),
    (
        "Benefits",
        "Enrollment window for the new health plan",
        "When does the enrollment window for the upgraded health plan open?",
    ),
    (
        "Policy",
        "Remote work equipment expense reimbursement",
        "Can I expense a second monitor under the hybrid work policy?",
    ),
    (
        "Other",
        "Gratuity calculation for a completed 5-year term",
        "How is gratuity calculated for employees completing five years?",
    ),
]
_PRIORITIES = ["Low", "Medium", "High", "Urgent"]
_STATUS_CYCLE = [
    ("Open", None, 0.0),  # unassigned, no stamps
    ("In Progress", 2.0, 0.0),  # assigned, agent picked up
    ("Waiting on Employee", 1.0, 0.0),  # assigned, employee owes a turn
    ("Resolved", 0.0, 25.0),  # resolved in ~a day
    ("Closed", 1.0, 25.0),  # closed by the agent
]


def _demo_rows(count: int) -> list[tuple[str, str, str, str]]:
    """Deterministic (category, subject, description, priority) rows for
    `count` tickets — wrapped templates get a stable `(batch N)` suffix and
    priorities rotate, so a rerun with the same count produces the exact
    same subject set (idempotency anchor)."""
    rows = []
    for i in range(count):
        category, subject, description = _TEMPLATES[i % len(_TEMPLATES)]
        priority = _PRIORITIES[i % len(_PRIORITIES)]
        batch = i // len(_TEMPLATES)
        if batch > 0:
            subject = f"{subject} (batch {batch + 1})"
        rows.append((category, subject, description, priority))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=30, help="demo ticket target (default 30)")
    parser.add_argument("--reset", action="store_true", help="delete all (DEMO) tickets first")
    args = parser.parse_args()

    from app import config as app_config

    if not app_config.DATABASE_URL:
        print("DATABASE_URL is not set — copy .env.example to .env first.")
        return 1

    now = datetime.now(timezone.utc)
    with psycopg.connect(app_config.DATABASE_URL, row_factory=dict_row) as connection:
        users = connection.execute(
            "SELECT id, name, role FROM users ORDER BY created_at"
        ).fetchall()
        employees = [u for u in users if u["role"] == "employee"]
        agents = [u for u in users if u["role"] == "agent"]
        print(
            f"Found {len(users)} accounts: {len(employees)} employee(s), "
            f"{len(agents)} agent(s), "
            f"{sum(1 for u in users if u['role'] == 'admin')} admin(s)"
        )
        if not employees or not agents:
            print("Need at least one employee and one agent account — none found.")
            return 1

        existing = {
            row["subject"]
            for row in connection.execute(
                "SELECT subject FROM tickets WHERE subject LIKE %s", (MARKER + "%",)
            ).fetchall()
        }
        if args.reset:
            deleted = connection.execute(
                "DELETE FROM tickets WHERE subject LIKE %s RETURNING subject", (MARKER + "%",)
            ).fetchall()
            print(f"Reset: removed {len(deleted)} demo row(s).")
            existing.clear()

        planned = _demo_rows(args.count)
        pending = [row for row in planned if f"{MARKER}{row[1]}" not in existing]
        skipped = len(planned) - len(pending)
        if not pending:
            print(f"Nothing to do — {skipped} demo row(s) already present.")
            return 0

        # Round-robin employees/agents; stagger over ~3 weeks so charts and
        # ordering look realistic (created spread, updated a bit later).
        inserted = 0
        for i, (category, subject, description, priority) in enumerate(pending):
            employee = employees[i % len(employees)]
            status, reply_hours, closed_after_days = _STATUS_CYCLE[i % len(_STATUS_CYCLE)]
            assignee = agents[i % len(agents)]
            created = now - timedelta(days=(i * 3) % 21, hours=(i * 7) % 24)
            updated = created + timedelta(minutes=(i * 37) % 180)
            resolved = created + timedelta(days=closed_after_days) if closed_after_days else None
            first_reply = created + timedelta(hours=reply_hours) if reply_hours else None
            closed_by = assignee["id"] if status == "Closed" else None

            new_id = str(uuid4())
            ticket = connection.execute(
                """
                INSERT INTO tickets (
                  id, employee_id, assignee_id, category, subject, description,
                  priority, status, created_at, updated_at, first_reply_at,
                  resolved_at, closed_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, ref
                """,
                (
                    new_id,
                    employee["id"],
                    assignee["id"] if status != "Open" else None,
                    category,
                    MARKER + subject,
                    description,
                    priority,
                    status,
                    created,
                    updated,
                    first_reply,
                    resolved,
                    closed_by,
                ),
            ).fetchone()

            if reply_hours:  # the pickup reply mirrors assignment flow data
                connection.execute(
                    """
                    INSERT INTO replies (id, ticket_id, author_id, author_role, body, created_at)
                    VALUES (%s, %s, %s, 'agent', %s, %s)
                    """,
                    (
                        str(uuid4()),
                        new_id,
                        assignee["id"],
                        "Thanks for raising this — I've picked it up and will get back "
                        "to you shortly.",
                        first_reply,
                    ),
                )
            inserted += 1
            if inserted <= 3 or inserted % 10 == 0:
                print(
                    f"  inserted {ticket['ref']}: {MARKER}{subject} ({status}, {employee['name']}, {priority})"
                )

        connection.commit()
        by_employee = {}
        for row in connection.execute(
            "SELECT u.name, count(*) AS total FROM tickets t JOIN users u ON u.id = t.employee_id"
            " WHERE t.subject LIKE %s GROUP BY u.name ORDER BY total DESC",
            (MARKER + "%",),
        ).fetchall():
            by_employee[row["name"]] = row["total"]
        print(f"Inserted {inserted} demo ticket(s) (skipped {skipped} existing).")
        for name, total in by_employee.items():
            print(f"  {name}: {total}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
