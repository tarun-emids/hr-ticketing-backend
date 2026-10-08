"""Notification rows (public.notifications).

Channel-agnostic store (channel='in_app' today) for in-app notifications.
All isolation is enforced here: list/mark methods only ever touch rows whose
recipient_id matches the acting user.
"""
from app.repositories.base import SupabaseRepository, rows_of


class NotificationRepository(SupabaseRepository):
    TABLE_NAME = "notifications"

    # -- writes ------------------------------------------------------------

    def insert_rows(self, rows: list[dict]) -> list[dict]:
        return rows_of(self.table().insert(rows).select("id"))

    # -- reads (all hard-scoped to the acting user) -------------------------

    def list_for_recipient(
        self, user_id: str, *, unread_only: bool, fetch_limit: int, offset: int
    ) -> list[dict]:
        """Newest-first. Windows with limit(offset+limit) then slices in
        Python, exactly like the original endpoint did (offset applies after
        filtering, chronologically — not unread-first)."""
        query = (
            self.table()
            .select("*")
            .eq("recipient_id", user_id)
            .order("created_at", desc=True)
            .limit(offset + fetch_limit)
        )
        if unread_only:
            query = query.eq("read", False)
        return rows_of(query)[offset:]

    def unread_rows(self, user_id: str) -> list[dict]:
        return rows_of(
            self.table().select("id").eq("recipient_id", user_id).eq("read", False)
        )

    # -- reads (background jobs) -------------------------------------------

    def prior_sla_thresholds(self, ticket_uuid: str) -> set:
        """Thresholds already notified for one ticket — the sweep fires at most
        once per ticket/threshold."""
        prior = rows_of(
            self.table().select("payload").eq("ticket_id", ticket_uuid).eq("type", "sla_breached")
        )
        return {p.get("payload", {}).get("thresholdHours") for p in prior}

    def ids_of_read_older_than(self, iso_cutoff: str) -> list[dict]:
        return rows_of(
            self.table().select("id").eq("read", True).lt("created_at", iso_cutoff)
        )

    def ids_of_any_older_than(self, iso_cutoff: str) -> list[dict]:
        return rows_of(self.table().select("id").lt("created_at", iso_cutoff))

    def delete_row(self, notification_id: str) -> None:
        self.table().delete().eq("id", notification_id).execute()

    # -- writes (read receipts) --------------------------------------------

    def mark_read(self, notification_id: str, user_id: str, read_at: str) -> list[dict]:
        """Mark one row read; rows not owned by user_id simply don't match."""
        return rows_of(
            self.table()
            .update({"read": True, "read_at": read_at})
            .eq("id", notification_id)
            .eq("recipient_id", user_id)
            .select("*")
        )

    def mark_all_read(self, user_id: str, read_at: str) -> list[dict]:
        return rows_of(
            self.table()
            .update({"read": True, "read_at": read_at})
            .eq("recipient_id", user_id)
            .eq("read", False)
            .select("*")
        )
