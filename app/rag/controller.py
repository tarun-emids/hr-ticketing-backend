"""HR assistant endpoints — the thin HTTP face over RagService.

The viewer contract matches every other person-bound endpoint (viewerId/
employeeId is the signed-in account; the role is re-resolved server-side, so
the chat can never widen a viewer's knowledge-base visibility).
"""

from fastapi import APIRouter, Depends

from app.deps import get_rag_service
from app.models import AssistantQuestion
from app.rag.service import RagService

router = APIRouter(prefix="/assistant", tags=["hr-assistant"])


@router.post("/ask")
def ask(question: AssistantQuestion, svc: RagService = Depends(get_rag_service)):
    """POST /assistant/ask — one grounded answer with [REF ¶block] citations.

    Stateless by design: no conversation history is stored or returned, and
    every exchange is audited server-side (assistant_queries)."""
    return svc.ask(question.employee_id, question.question)
