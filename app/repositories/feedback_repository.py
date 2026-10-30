"""PostgreSQL feedback rows (ticket-closure ratings)."""

from typing import Optional

from psycopg_pool import ConnectionPool

from app.repositories.base import as_uuid, first_of, insert_row, update_row

class FeedbackRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def get_for_ticket(self, ticket_uuid: str) -> Optional[dict]:
        return first_of(
            self._database,
            "select * from feedback where ticket_id = %s limit 1",
            (as_uuid(ticket_uuid),),
            table="feedback",
        )

    def insert_feedback(self, row: dict) -> dict:
        return insert_row(self._database, "feedback", row)

    def update_feedback(self, feedback_uuid: str, patch: dict) -> dict:
        update_row(self._database, "feedback", feedback_uuid, patch)
        return first_of(
            self._database,
            "select * from feedback where id = %s limit 1",
            (as_uuid(feedback_uuid),),
            table="feedback",
        )