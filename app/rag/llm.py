"""Google Gemini chat-completions client (Gemini's OpenAI-compatible endpoint).

One concern: turn a message list into assistant text, mapping every upstream
failure mode into either a breaker-counting outage or a user-facing
HTTPException. Prompt construction is NOT here — the service owns the
answer/citation contract (see app/rag/service.py).
"""

import time

import httpx
from fastapi import HTTPException

from app.rag import settings
from app.rag.embeddings import (  # same provider, same rules
    transient,
    upstream_failure,
)
from app.resilience import CircuitOpenError, assistant_breaker


def chat(messages: list[dict]) -> str:
    """One chat-completion over the configured Gemini model. Returns the raw
    assistant text — interpretation/citation handling lives in the service."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "HR assistant is not configured — set RAG_GEMINI_API_KEY (a Google "
                "Gemini API key from aistudio.google.com) to enable it."
            ),
        )

    def _one():
        payload: dict = {
            "model": settings.CHAT_MODEL,
            "messages": messages,
            "max_tokens": settings.CHAT_MAX_TOKENS,
        }
        if settings.CHAT_REASONING:
            # OpenAI-compat reasoning budget -> Gemini thinking budget. Empty
            # string (RAG_CHAT_REASONING= key set to nothing) omits the param
            # entirely, i.e. model default behavior.
            payload["reasoning_effort"] = settings.CHAT_REASONING
        res = httpx.post(
            settings.CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            # Cap the DIAL at 10s separately: without it a slow provider
            # handshake eats the whole read budget, stretching worst-case
            # waits past the configured read limit.
            timeout=httpx.Timeout(settings.CHAT_TIMEOUT_S, connect=10.0),
        )
        if res.status_code >= 400:
            # Same exception and status plain raise_for_status() would raise —
            # the breaker still classifies by status code — but the message
            # now carries Google's JSON body (model not found, quota, etc.).
            raise httpx.HTTPStatusError(
                f"HTTP {res.status_code} from provider: {res.text[:300]}",
                request=res.request,
                response=res,
            )
        return res.json()

    def _request():
        # Bounded transparent retry (shared policy with the embeddings client):
        # read/connect timeouts and brief provider overload get quick second
        # chances; everything else propagates on the first attempt.
        remaining = settings.RETRY_ATTEMPTS
        while True:
            try:
                return _one()
            except httpx.HTTPError as exc:
                if not transient(exc) or remaining <= 0:
                    raise
                remaining -= 1
                time.sleep(settings.RETRY_BACKOFF_S)

    try:
        data = assistant_breaker.call(_request, is_failure=upstream_failure)
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=503,
            detail="HR assistant is temporarily unavailable — try again shortly.",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The HR assistant chat provider is slow to respond — capacity "
                "is strained; try again shortly."
            ),
        ) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        # Keep the provider's own words in the detail: Google's body says
        # exactly WHY it failed (overload, quota, model retirement), turning
        # every future incident into a one-look diagnosis. 503-family
        # provider overload surfaces as OUR 503; other statuses as 502.
        raise HTTPException(
            status_code=503 if code in (429, 502, 503) else 502,
            detail=(
                f"HR assistant chat provider unavailable (HTTP {code}). "
                f"Provider says: {exc.response.text[:240]}"
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"HR assistant chat provider error: {exc}",
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
