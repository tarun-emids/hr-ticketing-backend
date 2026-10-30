"""Remove the seeded demo set in one command: every ticket whose subject is
marked "(DEMO) " — replies and notifications go with the ticket rows via the
schema's FK cascades, so this is the single delete point for the showcase set.

Usage:
    python scripts/remove_demo_data.py            # deletes (with confirmation)
    python scripts/remove_demo_data.py --yes      # no prompt
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")
import psycopg  # noqa: E402


def main() -> int:
    if "--yes" not in sys.argv:
        answer = (
            input("Delete every '(DEMO)%' ticket (replies/notifications cascade too)? [y/N] ")
            .strip()
            .lower()
        )
        if answer not in ("y", "yes"):
            print("Aborted — nothing deleted.")
            return 0
    load_dotenv()
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL missing — create backend/.env first.", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        counts = {}
        for table in ("replies", "notifications"):
            counts[table] = cur.execute(
                f"SELECT count(*) FROM {table} t JOIN tickets s ON s.id = t.ticket_id"
                " WHERE s.subject LIKE '(DEMO)%'"
            ).fetchone()[0]
        cur.execute("DELETE FROM tickets WHERE subject LIKE '(DEMO)%'")
        deleted = cur.rowcount
        print(
            f"deleted tickets: {deleted} (replies: {counts['replies']}, "
            f"notifications: {counts['notifications']} cascaded)"
        )
        if deleted == 0:
            print("Nothing to remove — the demo set isn't in the database.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
