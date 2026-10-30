"""Feedback service - submit ticket closure ratings under the guard rules.

Guards run in the fixed order: ticket exists -> caller known -> caller owns
the ticket -> ticket closed. A re-submission while Closed REPLACES the row
(200); the UNIQUE(ticket_id) constraint breaks ties for concurrent first
submissions (caught as the 400 that base.run raises on SQLSTATE 23xxx).
"""

from fastapi import HTTPException

from app.models import feedback_out
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.ticket_service import TicketNotFound


class FeedbackService:
    def __init__(
            self,
            feedbacks: FeedbackRepository,
            tickets: TicketRepository,
            users: UserRepository):
        self._feedbacks = feedbacks
        self._tickets = tickets
        self._users = users

    def submit(self, tid: str, *, user_id: str, rating: int, comment: str) -> tuple[dict, bool]:
        """POST /tickets/{tid}/feedback. Returns (serialized_feedback, created)."""
        ticket=self._tickets.get_by_key(tid)
        if not ticket:
            raise TicketNotFound()

        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=403, detail="Unknown user.")

        if user["id"] != ticket["employee_id"]:
            raise HTTPException(
                status_code=403,
                detail="Only the ticket's employee can submit feedback.",
            )

        if ticket["status"] != "Closed":
            raise HTTPException(
                status_code=409,
                detail=f"Ticket {ticket['ref']} is {ticket['status']}; "
                "feedback opens once it is Closed.",
            )

        existing = self._feedbacks.get_for_ticket(ticket["id"])
        if existing:
            return self._replace(existing, rating, comment), False

        try:
            row = self._feedbacks.insert_feedback(
                {
                    "ticket_id": ticket["id"],
                    "employee_id": user["id"],
                    "rating": rating,
                    "comment": comment.strip(),
                }
            )
            return feedback_out(row, ticket["ref"]), True
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
            row = self._feedbacks.get_for_ticket(ticket["id"])
            if not row:
                raise
            return self._replace(row, rating, comment), False


    def _replace(self, existing: dict, rating: int, comment: str) -> dict:
        return self._feedbacks.update_feedback(
            existing["id"], {"rating": rating, "comment": comment.strip()}
        )

    def get(self, tid: str, *, user_id: str) -> dict:
        """GET /tickets/{tid}/feedback?userId= - employee-owned read, agents
        bypass. 404 "has no feedback" is an empty result, not a bad route."""
        ticket = self._tickets.get_by_key(tid)
        if not ticket:
            raise TicketNotFound()

        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=403, detail="Unknown user.")

        if user["role"] != "agent" and user["id"] != ticket["employee_id"]:
            raise HTTPException(
                status_code=403,
                detail="Only the ticket's employee or an HR agent can view feedback.",
            )

        row = self._feedbacks.get_for_ticket(ticket["id"])
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket {ticket["ref"]} has no feedback."
            )
        return feedback_out(row, ticket["ref"])