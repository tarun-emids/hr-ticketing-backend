"""Set or reset the initial password for provisioned HR Desk users."""

import argparse
import getpass
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import close_database, get_database  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.passwords import hash_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set the password used by the HR Desk PostgreSQL login."
    )
    parser.add_argument(
        "--password",
        help="Initial password (min 12 characters). Falls back to "
        "HR_DESK_TEMP_PASSWORD, then a hidden interactive prompt.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation before replacing account password hashes.",
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
    accounts = users.accounts()
    if not accounts:
        print("The users table is empty — run schema.sql first.", file=sys.stderr)
        return 1

    print(f"Setting a password for {len(accounts)} account(s).")
    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted — no changes made.")
            return 0

    for account in accounts:
        users.set_password_hash(account["id"], hash_password(password))
        print(f"  password set for {account['email']} ({account['role']})")

    print(f"\nDone. updated={len(accounts)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        close_database()
