"""Authentication service.

The frontend never talks to Supabase Auth directly: credentials are checked
server-side against Supabase Auth (GoTrue password grant), and the result is
joined with the HR Desk account row in public.users (name + role) before the
app-level user is returned to the frontend.

No password, token or key is ever stored, logged or echoed here, and there is
deliberately no signup endpoint — accounts are provisioned by the organisation
(scripts/provision_auth_users.py), matching the internal-helpdesk model.

Layering note: this is the one service that reaches out to a *second*
Supabase surface (GoTrue). The throwaway per-grant client lives in _grant()
with the rationale below; account resolution goes through the injected
UserRepository (service-key backed, RLS bypassed).
"""
import re
from typing import Any

from fastapi import HTTPException

from app.config import SERVICE_KEY, SUPABASE_URL
from app.models import user_out
from app.repositories.user_repository import UserRepository


def _load_auth_api_error():
    """Version-proof AuthApiError source.

    supabase-py shipped its auth client as `gotrue` for years; recent releases
    rebrand it to `supabase_auth` (the standalone `gotrue` distribution is gone,
    while `supabase`/`postgrest` remain). Try both module names; if neither
    exists, callers fall back to duck-typing below — the class name itself is
    still "AuthApiError" and it still carries `.status`/`.code` + `.message`.
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


def _is_grant_error(e: BaseException) -> bool:
    """GoTrue response error (bad credentials etc.) vs transport failure.

    Class-based where the class could be imported; otherwise duck-typed on the
    class name / attribute trio that every supabase-py generation ships.
    """
    if AuthApiError is not None and isinstance(e, AuthApiError):
        return True
    if "AuthApiError" in type(e).__name__:
        return True
    return hasattr(e, "message") and (hasattr(e, "status") or hasattr(e, "code"))


def _grant_status(e: BaseException) -> int:
    raw = getattr(e, "status", None) or getattr(e, "code", None) or 400
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 400


def _go_true_user(res: Any) -> Any:
    """Version-proof access to the GoTrue user on an AuthResponse."""
    if isinstance(res, dict):
        return res.get("user")
    return getattr(res, "user", None)


def _like_safe(email: str) -> str:
    """Escape LIKE wildcards so emails with _ or % match exactly."""
    return email.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


# Characters that ride along in pasted emails and are invisible in the UI:
# zero-width spaces/marks/joiners, soft hyphen, BOM, bidi controls/isolates,
# and non-ASCII whitespace (NBSP etc.). strip() alone leaves all of these in,
# which turns the public.users lookup key into something that never matches.
# Built from chr() code points — pure-ASCII source, keeps it reviewable and
# immune to editors/pipelines that mangle literal unicode glyphs.
def _invisible_chars_pattern() -> str:
    ranges = [
        (0x200B, 0x200F),  # ZWSP, ZWNJ, ZWJ, LRM, RLM
        (0x2028, 0x202F),  # line/para separators + bidi embeds/overrides
        (0x2060, 0x2064),  # word joiner et al.
        (0x2066, 0x206F),  # bidi isolates + deprecated disambiguation
        (0x00AD, 0x00AD),  # soft hyphen
        (0xFEFF, 0xFEFF),  # BOM / zero-width no-break space
        (0x00A0, 0x00A0),  # NBSP
        (0x1680, 0x1680),  # ogham space mark
        (0x2000, 0x200A),  # en/em/thin spaces etc.
        (0x205F, 0x205F),  # medium mathematical space
        (0x3000, 0x3000),  # ideographic space
    ]
    parts = []
    for lo, hi in ranges:
        first, last = re.escape(chr(lo)), re.escape(chr(hi))
        parts.append(first if lo == hi else f"{first}-{last}")
    return "[" + "".join(parts) + "]"


_INVISIBLE_CHARS = re.compile(_invisible_chars_pattern())


def clean_email(raw: str) -> str:
    """Trim, strip invisible characters and lowercase an email."""
    return _INVISIBLE_CHARS.sub("", raw.strip()).lower()


def _grant(email: str, password: str) -> Any:
    """Perform the GoTrue password grant on a fresh, throwaway client.

    WHY: sign_in_with_password stores the USER session on whatever client
    runs it, and supabase-py then sends that user's JWT on LATER .table()
    reads built after the grant. public.users has RLS deny-all by design,
    so a query executed as the user instead of the service role silently
    filters every row to [] — no error, no rows (this is exactly the bug
    this endpoint used to have). Creating a fresh client per grant keeps
    the process-wide get_client() singleton permanently service-role-pure,
    so the account join below — and every other repository (tickets, users,
    meta, attachments) — keeps bypassing RLS server-side as designed.
    """
    from supabase import create_client

    return create_client(SUPABASE_URL, SERVICE_KEY).auth.sign_in_with_password(
        {"email": email, "password": password}
    )


class AuthService:
    def __init__(self, users: UserRepository):
        self._users = users

    def login(self, email: str, password: str) -> dict:
        """POST /api/auth/login core — real password sign-in.

        1. Verify email + password with Supabase Auth (GoTrue password grant).
        2. Resolve the public.users row by email for the app-level id/name/role.
        """
        email = clean_email(email)

        try:
            res = _grant(email, password)
        except Exception as e:
            if not _is_grant_error(e):
                raise HTTPException(
                    status_code=502,
                    detail="Could not reach the authentication service — try again shortly.",
                ) from e
            message = str(getattr(e, "message", "") or e).lower()
            status = _grant_status(e)
            if "not confirmed" in message:
                raise HTTPException(
                    status_code=403,
                    detail="Email not confirmed yet — contact HR/IT to activate this account.",
                )
            if status in (400, 401):
                # GoTrue's message for wrong credentials is already generic across
                # versions; normalise everything a bad grant can return to one line.
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            if status == 422:
                raise HTTPException(
                    status_code=400, detail="That doesn't look like a valid email address."
                )
            raise HTTPException(
                status_code=502,
                detail="Authentication service is unavailable — try again shortly.",
            )

        # Account resolution is server-to-server with the service role key
        # (get_client() is never used for a sign-in, so its reads stay clean).
        # Match case-insensitively (GoTrue stores emails lowercased, but rows in
        # public.users may have been entered with different casing).
        go_user = _go_true_user(res)
        go_email = clean_email(getattr(go_user, "email", None) or email)
        row = self._users.get_by_email_case_insensitive(_like_safe(go_email))
        if not row:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Password OK, but no HR Desk account exists for "
                    f"'{go_email}' yet. Ask HR/IT to add that email to the "
                    "account list (public.users) — scripts/provision_auth_users.py "
                    "creates matching credentials for every row."
                ),
            )

        return {"user": user_out(row)}
