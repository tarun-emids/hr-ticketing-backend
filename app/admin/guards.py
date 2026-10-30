"""Admin authorization rules (shared by every admin controller endpoint).

The app has no bearer tokens today; its trust anchor — everywhere — is the
account row resolved server-side from an id the client passes. These guards
apply the SAME anchor to privileged operations:

- `require_admin(users, actor_id)`: the acting account must exist AND carry
  the admin role, else 404/403. Mutations never trust a client-side claim.
- `require_self_or_admin(users, actor_id, target_id)`: agents may pull only
  their own performance; admins may pull anyone's.

Answers stay generic (an unknown id and a wrong-but-existing id answer
differently on purpose: the console distinguishes "no such account" from
"not allowed" the way the KB distinguishes 404/403).
"""

from typing import Optional

from fastapi import HTTPException

from app.repositories.base import UUID_RE
from app.repositories.user_repository import UserRepository


def require_account(
    users: UserRepository, actor_id: Optional[str], detail_msg: str = "(uuid required)"
) -> dict:
    """Resolve actor_id to a real account row (422 malformed, 404 unknown)."""
    if not actor_id or not isinstance(actor_id, str) or not UUID_RE.match(actor_id):
        raise HTTPException(status_code=422, detail=f"actorId {detail_msg} is required")
    account = users.get_by_id(actor_id)
    if not account:
        raise HTTPException(status_code=404, detail="Unknown account")
    return account


def require_admin(users: UserRepository, actor_id: Optional[str]) -> dict:
    """403 unless the acting account is an admin. Called by EVERY admin
    endpoint before any work happens."""
    account = require_account(users, actor_id)
    if account.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return account


def require_self_or_admin(
    users: UserRepository, actor_id: Optional[str], target_id: Optional[str]
) -> tuple[dict, dict]:
    """Agents may view their own performance only; admins everyone's.

    Returns (actor_account, target_account). Unknown target: 404; a
    non-admin actor querying somebody else: 403.
    """
    actor = require_account(users, actor_id)
    target = require_account(users, target_id)
    if actor.get("role") != "admin" and actor["id"] != target["id"]:
        raise HTTPException(
            status_code=403, detail="You can only view your own performance."
        )
    return actor, target
