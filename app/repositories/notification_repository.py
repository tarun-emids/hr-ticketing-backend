"""PostgreSQL access to private in-app notifications."""

from datetime import datetime

from psycopg_pool import ConnectionPool

from app.repositories.base import UUID_RE, as_uuid, insert_many_rows, rows_of, run


class NotificationRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def insert_rows(self, rows: list[dict]) -> list[dict]:
        return insert_many_rows(self._database, "notifications", rows, json_columns=("payload",))

    def list_for_recipient(
        self, user_id: str, *, unread_only: bool, fetch_limit: int, offset: int
    ) -> list[dict]:
        query = "SELECT * FROM notifications WHERE recipient_id = %s"
        params = [as_uuid(user_id)]
        if unread_only:
            query += " AND read = FALSE"
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend((fetch_limit, offset))
        return rows_of(self._database, query, tuple(params), table="notifications")

    def unread_rows(self, user_id: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT id FROM notifications WHERE recipient_id = %s AND read = FALSE",
            (as_uuid(user_id),),
            table="notifications",
        )

    def prior_sla_thresholds(self, ticket_uuid: str) -> set:
        prior = rows_of(
            self._database,
            "SELECT payload FROM notifications WHERE ticket_id = %s AND type = %s",
            (as_uuid(ticket_uuid), "sla_breached"),
            table="notifications",
        )
        return {row.get("payload", {}).get("thresholdHours") for row in prior}

    def ids_of_read_older_than(self, iso_cutoff: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT id FROM notifications WHERE read = TRUE AND created_at < %s",
            (datetime.fromisoformat(iso_cutoff.replace("Z", "+00:00")),),
            table="notifications",
        )

    def ids_of_any_older_than(self, iso_cutoff: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT id FROM notifications WHERE created_at < %s",
            (datetime.fromisoformat(iso_cutoff.replace("Z", "+00:00")),),
            table="notifications",
        )

    def delete_row(self, notification_id: str) -> None:
        run(
            self._database,
            "DELETE FROM notifications WHERE id = %s",
            (as_uuid(notification_id),),
            fetch="none",
            table="notifications",
        )

    def mark_read(self, notification_id: str, user_id: str, read_at: str) -> list[dict]:
        if not UUID_RE.fullmatch(notification_id) or not UUID_RE.fullmatch(user_id):
            return []
        return rows_of(
            self._database,
            "UPDATE notifications SET read = TRUE, read_at = %s "
            "WHERE id = %s AND recipient_id = %s RETURNING *",
            (
                datetime.fromisoformat(read_at.replace("Z", "+00:00")),
                as_uuid(notification_id),
                as_uuid(user_id),
            ),
            table="notifications",
        )

    def mark_all_read(self, user_id: str, read_at: str) -> list[dict]:
        return rows_of(
            self._database,
            "UPDATE notifications SET read = TRUE, read_at = %s "
            "WHERE recipient_id = %s AND read = FALSE RETURNING *",
            (datetime.fromisoformat(read_at.replace("Z", "+00:00")), as_uuid(user_id)),
            table="notifications",
        )
