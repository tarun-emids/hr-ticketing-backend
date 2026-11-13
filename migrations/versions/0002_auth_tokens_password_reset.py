"""Auth tokens + password reset storage.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04

Release-new schema for the login-enhancement work (bearer access tokens and
the Mailpit OTP reset flow):

  * users.auth_version — cached-credential epoch for issued tokens: every
    password change bumps it, which instantly invalidates old tokens.
  * password_reset_otps — one pending OTP challenge per user (attempts
    capped at 5).

Both statements are guarded (IF NOT EXISTS) on purpose: databases that were
bootstrapped by the CURRENT schema.sql (which already carries these objects)
stamp at 0001 and then apply this revision — the guards let it land without
erroring on the objects that are already there. A database built purely by
migrations gets the same result through the plain path.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS = [
    """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_version
      integer NOT NULL DEFAULT 0
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_otps (
      user_id    uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
      otp_hash   text NOT NULL,
      expires_at timestamptz NOT NULL,
      attempts   integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
]

DOWNGRADE_STATEMENTS = [
    "DROP TABLE IF EXISTS password_reset_otps",
    "ALTER TABLE users DROP COLUMN IF EXISTS auth_version",
]


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
