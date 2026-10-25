"""Hugging Face chat-completions client (OpenAI-compatible HF router).

One concern: turn a message list into assistant text, mapping every upstream
failure mode into either a breaker-counting outage or a user-facing
HTTPException. Prompt construction is NOT here — the service owns the
answer/citation contract (see app/rag/service.py).
"""

import httpx
from fastapi import HTTPException

from app.rag import settings
from app.rag.embeddings import upstream_failure  # same provider, same rules
from app.resilience import CircuitOpenError, assistant_breaker


def chat(messages: list[dict]) -> str:
    """One chat-completion over the configured HF model. Returns the raw
    assistant text — interpretation/citation handling lives in the service."""
    if not settings.HF_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                "HR assistant is not configured — set RAG_HF_TOKEN (a Hugging Face "
                "Inference token) to enable it."
            ),
        )

    def _request():
        res = httpx.post(
            settings.CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.HF_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.CHAT_MODEL,
                "messages": messages,
                "max_tokens": settings.CHAT_MAX_TOKENS,
            },
            timeout=settings.CHAT_TIMEOUT_S,
        )
        res.raise_for_status()
        return res.json()

    try:
        data = assistant_breaker.call(_request, is_failure=upstream_failure)
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=503,
            detail="HR assistant is temporarily unavailable — try again shortly.",
        ) from exc
    return parse_answer(data)


def parse_answer(data: object) -> str:
    """OpenAI-compatible payload -> assistant text ('choices[0].message'), in
    one tolerant place so downstream routers/payload drift stay contained."""
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="HR assistant provider returned an unexpected answer shape.",
        ) from exc
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(
            status_code=502,
            detail="HR assistant returned an empty answer.",
        )
    return text
