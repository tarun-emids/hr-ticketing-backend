"""Google Gemini embeddings client (OpenAI-compatible endpoint) + cosine search.

Two applications live here because both are inseparable from this module's
one concern — similarity scoring: turn text into vectors (Gemini embeddings),
and rank chunk vectors against a question vector. No pgvector: the library is
~30 documents / a few hundred paragraphs, so in-Python cosine wins on
simplicity and portability (plain REAL columns store nothing extra).

Failure classification (see app/resilience.py + the breaker contract):
transport errors, 5xx and 429 prove the PROVIDER is struggling and count
against the assistant breaker; 401/403/404 mean the key/model choice is
wrong — planner error, never a provider outage, so they stay neutral.
"""

import math
import time
from typing import Any

import httpx
from fastapi import HTTPException

from app.rag import settings
from app.resilience import CircuitOpenError, assistant_breaker


def transient(exc: BaseException) -> bool:
    """Worth a bounded second try? (both rag clients share this policy)
    Read/connect/write timeouts and provider overload (5xx/429) usually
    succeed on a quick retry; 401/403/404 mean the key/model choice is wrong
    — planner error, retrying would just waste the user's patience."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return False


def upstream_failure(exc: BaseException) -> bool:
    """Breaker predicate for Gemini upstream calls (both rag clients share it).
    5xx and 429 (plus every transport error) prove the PROVIDER struggles and
    count; 401/403/404 mean the key/model choice is wrong — caller problem,
    never an outage, so they stay neutral (see app/resilience.py docstring)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return True  # transport failures (connect/read/timeout), malformed responses


def _bearer() -> dict:
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "HR assistant is not configured — set RAG_GEMINI_API_KEY (a Google "
                "Gemini API key from aistudio.google.com) to enable it."
            ),
        )
    return {"Authorization": f"Bearer {settings.GEMINI_API_KEY}"}


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts (auto-chunked to the provider's batch cap).

    Returns exactly one vector per input, in order. Transient provider
    failures surface as HTTPException(502/503) with user-facing wording —
    callers never touch raw provider errors, and exhausted failures keep
    their status code so the API answers 502/503 respectively.
    """
    if not texts:
        return []
    out: list[list[float]] = []
    for start in range(0, len(texts), settings.EMBED_BATCH):
        out.extend(_embed_batch(texts[start : start + settings.EMBED_BATCH]))
    return out


def _embed_batch(batch: list[str]) -> list[list[float]]:
    def _one():
        res = httpx.post(
            settings.EMBED_URL,
            headers={**_bearer(), "Content-Type": "application/json"},
            json={
                "model": settings.EMBED_MODEL,
                "input": batch,
                "encoding_format": "float",  # Google's OpenAI-compat endpoint
                # requires explicit float (not base64)
            },
            # Cap the DIAL at 10s separately: without it a slow provider
            # handshake eats the whole read budget, stretching worst-case
            # waits past the configured read limit.
            timeout=httpx.Timeout(settings.EMBED_TIMEOUT_S, connect=10.0),
        )
        if res.status_code >= 400:
            # Same exception and status the plain raise_for_status() would
            # raise — the breaker still classifies by status code — but the
            # message now carries Google's JSON body (e.g. the real reason a
            # model 404s: "models/text-embedding-004 not found").
            raise httpx.HTTPStatusError(
                f"HTTP {res.status_code} from provider: {res.text[:300]}",
                request=res.request,
                response=res,
            )
        return res.json()

    def _request():
        # Bounded transparent retry: transient hiccups (timeouts, brief 5xx/429
        # overload) usually clear on a quick second try; the loop is capped so
        # total added latency is bounded and the breaker still sees one final
        # verdict per exchange instead of amplifying systemic outages.
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
                "The HR assistant provider is slow to respond — capacity is "
                "strained; try again shortly or rephrase."
            ),
        ) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        raise HTTPException(
            status_code=503 if code in (429, 502, 503) else 502,
            detail=(
                f"HR assistant embedding provider unavailable (HTTP {code}). "
                f"Provider says: {exc.response.text[:240]}"
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"HR assistant embedding provider error: {exc}",
        ) from exc

    if isinstance(data, dict) and data.get("error"):
        raise HTTPException(
            status_code=502,
            detail="The HR assistant provider rejected an embedding request.",
        )
    # OpenAI-style wrapper `{"data": [{...}]}` (Gemini) vs a bare list: one
    # extraction line keeps both payload shapes tolerable.
    raw = (
        data["data"]
        if isinstance(data, dict) and isinstance(data.get("data"), list)
        else data
        if isinstance(data, list)
        else [data]
    )
    try:
        vectors = [_normalize(vec) for vec in raw]
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="HR assistant provider returned an unexpected embedding shape.",
        ) from exc
    if len(vectors) != len(batch):
        raise HTTPException(
            status_code=502,
            detail="HR assistant provider returned an unexpected embedding shape.",
        )
    return vectors


def _normalize(vec: Any) -> list[float]:
    """Provider shapes drift: flat list, {"embedding": [...]}, or nested
    token embeddings (mean-pooled here). One normalizer covers all shapes."""
    if isinstance(vec, (list, tuple)):
        if vec and isinstance(vec[0], (list, tuple)):  # token-level -> sentence
            pooled = [0.0] * len(vec[0])
            for token_vector in vec:
                for i, value in enumerate(token_vector):
                    pooled[i] += value
            width = float(len(vec))
            return [value / width for value in pooled]
        return [float(value) for value in vec]
    if isinstance(vec, dict):
        for key in ("embedding", "vector", "features"):
            if isinstance(vec.get(key), list):
                return _normalize(vec[key])
    raise ValueError("Unrecognised embedding payload")


def cosine(a: list[float], b: list[float]) -> float:
    """Plain cosine similarity; 0.0 on empty or length-mismatched input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da * db)


def rank(question_vector: list[float], chunks: list[dict]) -> list[dict]:
    """Best-first copy of the chunk list, each + similarity `score` field."""
    scored = [(cosine(question_vector, chunk["embedding"]), chunk) for chunk in chunks]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{**chunk, "score": round(score, 6)} for score, chunk in scored]
