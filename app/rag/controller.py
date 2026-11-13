"""HR assistant endpoints — the thin HTTP face over RagService.

The viewer contract matches every other person-bound endpoint (viewerId/
employeeId is the signed-in account; the role is re-resolved server-side, so
the chat can never widen a viewer's knowledge-base visibility).
"""

from fastapi import APIRouter, Depends

from app.deps import acting_user_id, get_current_account, get_rag_service
from app.models import AssistantQuestion
from app.rag.service import RagService

router = APIRouter(prefix="/assistant", tags=["hr-assistant"])


@router.post("/ask")
def ask(
    question: AssistantQuestion,
    account: dict = Depends(get_current_account),
    svc: RagService = Depends(get_rag_service),
):
    """POST /assistant/ask — one grounded answer with [REF ¶block] citations.

    Stateless by design: no conversation history is stored or returned, and
    every exchange is audited server-side (assistant_queries). The asking
    employee comes from the bearer token, so the audit row and the visibility
    pool can never be widened by a client-supplied employeeId."""
    return svc.ask(acting_user_id(account, question.employee_id), question.question)
