"""Set initial local-demo passwords without overwriting existing passwords."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import close_database, get_database  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.passwords import hash_password  # noqa: E402

DEMO_EMAILS = (
    "priya@acme.com",
    "marcus@acme.com",
    "dana@acme.com",
    "tomas@acme.com",
    "alicia@acme.com",
    "ben@acme.com",
    "ruth@acme.com",
)


def main() -> int:
    password = os.getenv("HR_DESK_TEMP_PASSWORD", "ChangeMe123!")
    if len(password) < 12:
        print("HR_DESK_TEMP_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 2

    users = UserRepository(get_database())
    password_hash = hash_password(password)
    initialized = 0
    for email in DEMO_EMAILS:
        user = users.get_by_email_case_insensitive(email)
        if user is None:
            raise RuntimeError(f"Expected local demo account is missing: {email}")
        if not user.get("password_hash"):
            initialized += users.set_password_hash_if_missing(user["id"], password_hash)

    print(f"Initialized passwords for {initialized} local demo account(s) without passwords.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        close_database()
