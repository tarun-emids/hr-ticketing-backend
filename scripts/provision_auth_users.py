"""One-time account provisioning for the HR Desk (organisation-managed).

The HR Desk has no signup: accounts in public.users are activated here by
HR/IT, one Supabase Auth credential per row. Run once per environment (and
whenever someone is added to public.users):

    cd backend
    python scripts/provision_auth_users.py
    python scripts/provision_auth_users.py --password "Initial-pass-123"
    # or set HR_DESK_TEMP_PASSWORD in the environment before running

What it does
  - for every row in public.users, creates the matching Supabase Auth user
    (same email, email confirmed, chosen initial password — Supabase's
    default minimum is 6 characters),
  - skips accounts that already exist in Supabase Auth,
  - never prints or stores the password.

Passwords can be changed any time afterwards from the Supabase Dashboard
(Authentication -> Users) or by deleting the auth user and re-running this.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_client  # noqa: E402
from app.repositories.base import rows_of  # noqa: E402


def _load_auth_api_error():
    """Version-proof AuthApiError source.

    supabase-py shipped its auth client as `gotrue` for years; recent releases
    rebrand it to `supabase_auth` (the standalone `gotrue` distribution is
    gone). Try both module names; if neither exists, fall back to duck-typing —
    the class name is still "AuthApiError" and it still carries
    `.status`/`.code` + `.message`.
    """
    try:
        from gotrue.errors import AuthApiError  # supabase-py < 2.15

        return AuthApiError
    except ModuleNotFoundError:
        pass
    try:
        from supabase_auth.errors import AuthApiError  # supabase-py >= 2.15

        return AuthApiError
    except ModuleNotFoundError:
        return None


AuthApiError = _load_auth_api_error()

ALREADY_EXISTS_MARKERS = ("already", "registered", "signed up", "exists")


def _is_grant_error(e: BaseException) -> bool:
    """GoTrue response error vs transport failure. Mirrors the auth service."""
    if AuthApiError is not None and isinstance(e, AuthApiError):
        return True
    if "AuthApiError" in type(e).__name__:
        return True
    return hasattr(e, "message") and (hasattr(e, "status") or hasattr(e, "code"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Supabase Auth accounts for public.users rows."
    )
    parser.add_argument(
        "--password",
        help="Initial password (min 6 chars). Falls back to the "
        "HR_DESK_TEMP_PASSWORD env var, then to a hidden interactive prompt.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the (y/n) confirmation before touching Supabase Auth.",
    )
    args = parser.parse_args()

    password = (
        args.password
        or os.getenv("HR_DESK_TEMP_PASSWORD")
        or getpass.getpass("Initial password for provisioned accounts: ")
    )
    if len(password) < 6:
        print("Password must be at least 6 characters (Supabase default).", file=sys.stderr)
        return 2

    users = rows_of(
        get_client().table("users").select("id,name,email,role").order("created_at").execute()
    )
    if not users:
        print("public.users is empty — run backend/schema.sql first.", file=sys.stderr)
        return 1

    print(f"Provisioning {len(users)} account(s) against Supabase Auth.")
    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted — no changes made.")
            return 0

    created = skipped = failed = 0
    for u in users:
        try:
            get_client().auth.admin.create_user(
                {"email": u["email"], "password": password, "email_confirm": True}
            )
            line = f"  created  {u['email']:<22} ({u['role']})"
            created += 1
        except Exception as e:
            message = str(getattr(e, "message", "") or e).lower()
            if not _is_grant_error(e):
                line = f"  FAILED   {u['email']:<22} unexpected {type(e).__name__}: {e}"
                failed += 1
            elif any(marker in message for marker in ALREADY_EXISTS_MARKERS):
                line = f"  exists   {u['email']:<22} (skipped)"
                skipped += 1
            else:
                line = f"  FAILED   {u['email']:<22} {getattr(e, 'message', '') or e}"
                failed += 1
        print(line)

    print(f"\nDone. created={created} existing={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
