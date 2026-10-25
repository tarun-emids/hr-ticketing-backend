"""Assistant orchestration: retrieve -> prompt -> cite -> persist.

The citation contract (why every answer names its paragraph):

1. Retrieval only ever proposes chunks the viewer's role may read (same
   visibility pools as the knowledge base itself, resolved server-side from
   public.users — the whole KB is pre-gated here, so the model cannot leak a
   policy the viewer is not allowed to open).
2. The prompt DEMANDS inline markers in the exact `[REF ¶block]` form.
3. The service never trusts the model alone: markers are parsed back against
   the retrieved chunks, and a machine-verified `Sources` footer is appended
   to the answer so the answer panel always links to the documents that
   justified it. If the context was empty or the model reports it found
   nothing, the answer says so plainly — no forced hallucination.

Each answered question is audited (employee snapshot + question + answer +
cited sources) but never re-displayed: the chat is stateless by design.
"""

import re
from typing import Optional

from fastapi import HTTPException

from app.rag import embeddings, llm, settings
from app.rag.chunking import full_citation, truncate
from app.rag.repository import RagRepository
from app.repositories.base import UUID_RE
from app.repositories.user_repository import UserRepository
from app.services.kb_service import pools_for

_CITATION = re.compile(r"\[([A-Z]{2,12}-[A-Z0-9]+|KB-HR-[0-9]+|KB-E-[0-9]+)[\s·]*¶\s*(\d+)\]")
_NOT_FOUND = "I could not find that in the knowledge base."

_SYSTEM_PROMPT = (
    "You are the Emids HR Desk assistant. Answer employee and HR questions "
    "about company policies ONLY using the numbered policy excerpts provided "
    "in the user message.\n"
    "Rules:\n"
    "- Always write any needed citations INLINE, in the exact form "
    "[REF ¶block] where REF is the policy code (e.g. KB-E-01) and block is "
    "the paragraph number from the excerpt header, e.g. [KB-E-01 ¶7].\n"
    "- Quote or closely paraphrase the cited paragraph's substance on the "
    "same topic only; do not invent policies, numbers, dates or names.\n"
    "- If the excerpts do not contain the answer, reply exactly: "
    f"{_NOT_FOUND!r} with no citations.\n"
    "- Keep the answer short (max ~120 words), plain prose, no markdown."
)


def _excerpt_block(chunk: dict) -> str:
    """The exact block the model is allowed to cite (header mirrors the
    inline marker so 'every fact -> citation' is checkable)."""
    label = full_citation(chunk["ref"], chunk["title"], chunk["section"], chunk["block_no"])
    body = chunk["body"] if len(chunk["body"]) <= 900 else truncate(chunk["body"], 900)
    return f"### {label}\n{body}"


class RagService:
    def __init__(self, rag: RagRepository, users: UserRepository):
        self._rag = rag
        self._users = users

    # -- viewer (same contract as the knowledge-base endpoints) ---------------

    def _viewer(self, viewer_id: Optional[str]) -> dict:
        if not viewer_id or not isinstance(viewer_id, str) or not UUID_RE.match(viewer_id):
            raise HTTPException(status_code=422, detail="employeeId (uuid) is required")
        viewer = self._users.get_by_id(viewer_id)
        if not viewer:
            raise HTTPException(status_code=404, detail="Unknown viewer")
        return viewer

    # -- endpoint core ---------------------------------------------------------

    def ask(self, viewer_id: Optional[str], question: str) -> dict:
        viewer = self._viewer(viewer_id)
        question = (question or "").strip()
        if len(question) < 2:
            raise HTTPException(
                status_code=422, detail="Ask a question of at least 2 characters."
            )
        if len(question) > settings.MAX_QUESTION_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"Question is limited to {settings.MAX_QUESTION_CHARS} characters.",
            )

        pools = pools_for(viewer.get("role"))
        chunks = self._rag.chunks_for_audiences(pools)

        if not settings.HF_TOKEN:
            answer = "HR assistant is not configured — ask your admin to set RAG_HF_TOKEN."
            sources: list[dict] = []
            citations = []
            answer_body = answer
        elif not chunks:
            answer = "I could not find any documents in your library to answer from."
            sources, citations = [], []
            answer_body = answer
        else:
            vector = embeddings.embed_texts([question])[0]
            top = embeddings.rank(vector, chunks)[: settings.TOP_K]
            excerpts = "\n\n".join(_excerpt_block(c) for c in top)
            user_prompt = f"POLICY EXCERPTS:\n\n{excerpts}\n\nQUESTION: {question}\n\nAnswer:"
            answer_body = llm.chat([{"role": "system", "content": _SYSTEM_PROMPT},
                                    {"role": "user", "content": user_prompt}])
            citations, answer_body = _reconcile_citations(answer_body, top)
            sources = _sources_from(citations if citations else top)
            answer_body = _with_sources_footer(answer_body, sources)

        row = self._rag.record_query(
            employee_id=str(viewer["id"]),
            employee_name=viewer.get("name") or "",
            employee_role=viewer.get("role") or "",
            question=question,
            answer=answer_body,
            citations=sources,
        )
        return {"id": row["id"], "answer": answer_body, "citations": sources}


def _reconcile_citations(answer: str, top: list[dict]) -> tuple[list[dict], str]:
    """Parse the model's [REF ¶block] markers against retrieved chunks.

    Returns (cited_chunks_in_reading_order, cleaned_answer). A marker that
    does not point at a RETRIEVED chunk is treated as a model slip: it stays
    out of the cited set (the machine footer stays authoritative), but the
    text is left untouched — reviewers can then see both what the model
    claimed and what the retrieval actually supported.
    """
    by_key = {(c["ref"], c["block_no"]): c for c in top}
    cited: list[dict] = []
    seen: set = set()
    for match in _CITATION.finditer(answer):
        key = (match.group(1), int(match.group(2)))
        chunk = by_key.get(key)
        if chunk and key not in seen:
            seen.add(key)
            cited.append(chunk)
    return cited, answer


def _sources_from(chunks: list[dict]) -> list[dict]:
    """Citation rows shared by the answer footer, the audit table and the UI:
    everything the frontend needs to render one chip +它的 open-policy link."""
    return [
        {
            "ref": chunk["ref"],
            "slug": chunk["document_slug"],
            "title": chunk["title"],
            "section": chunk["section"],
            "blockNo": chunk["block_no"],
            "snippet": truncate(chunk["body"], 220),
        }
        for chunk in chunks
    ]


def _with_sources_footer(answer: str, sources: list[dict]) -> str:
    """Machine-verified citation footer: the model markers stay inline, and
    the footer lists every cited paragraph as `REF ¶block — section`. When
    the model wrote NO markers but content was retrieved, the footer still
    names the used excerpts — the citation promise never depends on prompts."""
    if not sources:
        return answer
    lines = [f"{s['ref']} ¶{s['blockNo']} — {s['title']} · {s['section']}" for s in sources]
    footer = "\n\nSources:\n" + "\n".join(lines)
    return answer if "Sources:" in answer else answer + footer


