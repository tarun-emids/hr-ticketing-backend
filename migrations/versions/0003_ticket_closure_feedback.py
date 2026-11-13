"""Ticket-closure feedback (PR #15) + optional existing-DB tolerance.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09

One rating (1-5) plus an optional comment per ticket, written by the
ticket's employee after closure. UNIQUE (ticket_id) prevents duplicates at
the database level (the service falls back to a replace), CHECKs keep the
row shape honest, and the updated_at trigger mirrors the other tables.

The statements are guarded (IF NOT EXISTS) so a database that was already
bootstrapped by the current schema.sql (which carries the feedback table
even before Alembic knew it) stamps past 0001/0002 and lands here without
erroring; a pure-migration database gets the same structure on the plain
path.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS = [
    r"""
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      ticket_id   uuid NOT NULL UNIQUE REFERENCES tickets (id) ON DELETE CASCADE,
      employee_id uuid NOT NULL REFERENCES users (id),
      rating      integer NOT NULL CHECK (rating BETWEEN 1 AND 5),
      comment     text NOT NULL DEFAULT '' CHECK (char_length(comment) <= 2000),
      created_at  timestamptz NOT NULL DEFAULT now(),
      updated_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    DROP TRIGGER IF EXISTS trg_feedback_updated ON feedback
    """,
    """
    CREATE TRIGGER trg_feedback_updated
      BEFORE UPDATE ON feedback
      FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """,
]

DOWNGRADE_STATEMENTS = [
    "DROP TRIGGER IF EXISTS trg_feedback_updated ON feedback",
    "DROP TABLE IF EXISTS feedback",
]


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
