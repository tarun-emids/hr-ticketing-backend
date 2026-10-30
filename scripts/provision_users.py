"""Provision the HR Desk demo accounts: ONE command that guarantees the
canonical 7 personas — 1 admin, 3 HR agents, 3 employees — with a shared
initial password.

Every run:
  1. creates any missing canonical account (so `schema.sql` re-runs are not
     required before provisioning),
  2. RESETS each canonical account's role to its canonical value (tomas is
     always admin; alicia/ben/ruth always agents; the others always
     employees — deliberate: promotions made in the admin console are
     personal actions, and re-provisioning restores the demo baseline),
  3. sets the SAME initial password on every account in the users table
     (including any you created through the admin console).

`--admin <email>` (legacy convenience) additionally promotes any OTHER
account to admin as well — unnecessary for the 7 canonical personas, whose
roles are already enforced above.

Canonical identity: emails follow `firstname@acme.com` with no role marker;
a person keeps their email across promotions/demotions.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from app.admin.repository import AdminRepository  # noqa: E402
from app.config import close_database, get_database  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.passwords import hash_password  # noqa: E402

# The demo cast — role is canonical per email, not per person: the address is
# the sign-in identity (see schema.sql's email-pattern note about .hr markers).
PERSONAS = [
    {"name": "Priya Sharma", "email": "priya@acme.com", "role": "employee"},
    {"name": "Marcus Webb", "email": "marcus@acme.com", "role": "employee"},
    {"name": "Dana Cole", "email": "dana@acme.com", "role": "employee"},
    {"name": "Tomas Nowak", "email": "tomas@acme.com", "role": "admin"},
    {"name": "Alicia Gomez", "email": "alicia@acme.com", "role": "agent"},
    {"name": "Ben Osei", "email": "ben@acme.com", "role": "agent"},
    {"name": "Ruth Meyer", "email": "ruth@acme.com", "role": "agent"},
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guarantee the 7 demo accounts (1 admin / 3 agents / 3 "
        "employees), align their roles, and set the shared "
        "initial password."
    )
    parser.add_argument(
        "--password",
        help="Initial password (min 12 characters). Falls back to "
        "HR_DESK_TEMP_PASSWORD, then a hidden interactive prompt.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation before replacing passwords and roles.",
    )
    parser.add_argument(
        "--admin",
        metavar="EMAIL",
        default="",
        help="Legacy convenience: additionally promote this (non-canonical) "
        "email to admin. The canonical admin (tomas@acme.com) is upheld "
        "by default now.",
    )
    parser.add_argument(
        "--keep-roles",
        action="store_true",
        help="Do NOT reset the personas' roles to canonical; only align "
        "membership, create missing accounts and set passwords. Use when "
        "a teammate's manual promotion must survive this run.",
    )
    args = parser.parse_args()

    password = (
        args.password
        or os.getenv("HR_DESK_TEMP_PASSWORD")
        or getpass.getpass("Initial password for provisioned accounts: ")
    )
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 2

    users = UserRepository(get_database())
    admin_repo = AdminRepository(get_database())
    pw_hash = hash_password(password)

    created, aligned = [], []
    for persona in PERSONAS:
        row = users.get_by_email_case_insensitive(persona["email"])
        if row is None:
            admin_repo.insert_account({**persona, "password_hash": pw_hash})
            created.append(persona["email"])
            print(f"  created:  {persona['email']} ({persona['role']})")
            continue
        current_role = row["role"]
        if (not args.keep_roles) and current_role != persona["role"]:
            admin_repo.set_role(row["id"], persona["role"])
            aligned.append(f"{persona['email']}: {current_role} -> {persona['role']}")
            print(f"  role aligned: {persona['email']} ({aligned[-1].split(': ')[-1]})")
        else:
            print(f"  role ok:    {persona['email']} ({persona['role']})")

    accounts = users.accounts()
    print(f"\nSetting the password for {len(accounts)} account(s).")
    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted — no changes made.")
            return 0

    for account in accounts:
        users.set_password_hash(account["id"], pw_hash)

    if args.admin:
        match = next(
            (a for a in accounts if a["email"].lower() == args.admin.strip().lower()),
            None,
        )
        if match and match["email"] not in {p["email"] for p in PERSONAS}:
            admin_repo.set_role(match["id"], "admin")
            print(f"  additionally promoted to admin: {match['email']}")
        else:
            print(
                f"  --admin: {args.admin} is a canonical persona (handled above) "
                "or not in the users table; skipped."
            )

    print(
        f"\nSummary: {len(created)} created, {len(aligned)} roles realigned, "
        f"{len(accounts)} passwords set."
    )
    print("Canonical state: 1 admin (tomas@acme.com), 3 agents, 3 employees.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # undefined table etc. → actionable message
        if "does not exist" in str(exc) and "users" in str(exc):
            print(
                "The users table does not exist yet — run schema.sql first "
                "(see START-HERE-GUIDE.md §4).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        raise
    finally:
        close_database()
