"""Assistant env configuration (reads app/config's already-loaded .env).

Every knob is env-tunable without a deploy. `RAG_GEMINI_API_KEY` (or plain
`GEMINI_API_KEY`) is the master switch: when it is empty the assistant
answers with a configuration notice instead of calling the network (and
seeding skips chunk embedding), so the feature is fully optional in every
environment.
"""

import os

# --- Google Gemini API (free tier: create a key at aistudio.google.com/apikey) ---
GEMINI_API_KEY = (
    os.getenv("RAG_GEMINI_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
)

# Chat: Gemini's OpenAI-compatible endpoint, so the request/response contract
# is the standard OpenAI chat shape (choices[0].message.content). If a model
# is retired, the provider 404s with the current model name in the message —
# set RAG_CHAT_MODEL to it (check https://ai.google.dev/gemini-api/docs/models).
# NOTE: retired for new keys: gemini-2.5-flash. gemini-3.8-flash serves but
# answered sustained 503s on a fresh key (2026-10-28) — the LITE alias lane
# is the default: fastest, high-capacity, no thinking phase.
CHAT_URL = os.getenv(
    "RAG_CHAT_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
)
CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", "gemini-flash-lite-latest")
# Reasoning budget (sent as the OpenAI-compat `reasoning_effort` param, which
# Google maps onto the model's thinking configuration). This API answers
# grounded factoids from retrieved excerpts — deep thinking adds latency, not
# accuracy. "low" keeps some reasoning guardrails; "none" is the fastest
# setting (allowed on Flash-class models; some Pro-class models reject it or
# only support "dynamic").
CHAT_REASONING = os.getenv("RAG_CHAT_REASONING", "low").strip().lower()
# First-token latency on a thinking-class chat model plus a slow uplink can
# legitimately exceed a minute — the read budget covers the WHOLE response.
CHAT_TIMEOUT_S = float(os.getenv("RAG_CHAT_TIMEOUT_S", "120"))
CHAT_MAX_TOKENS = int(os.getenv("RAG_CHAT_MAX_TOKENS", "512"))

# Embeddings: Gemini's OpenAI-compatible embeddings endpoint. gemini-
# embedding-001 is the recommended model — text-embedding-004 has been
# RETIRED on this endpoint (it answers 404 "not found"), so don't switch
# back. `input` accepts a batch array, so RAG_EMBED_BATCH still caps how
# much rides on one request — smaller batches also ride free-tier limits.
EMBED_URL = os.getenv(
    "RAG_EMBED_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/embeddings",
)
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "gemini-embedding-001")
EMBED_TIMEOUT_S = float(os.getenv("RAG_EMBED_TIMEOUT_S", "30"))
EMBED_BATCH = int(os.getenv("RAG_EMBED_BATCH", "32"))

# Bounded transparent retry for the two provider clients (app/rag): a read/
# connect timeout or an overloaded provider (5xx/429) gets up to
# RETRY_ATTEMPTS extra tries with RETRY_BACKOFF_S between them. Total extra
# wait stays bounded (attempts x backoff), so the circuit breaker still ends
# up limiting systemic failure across requests (it counts the ATTEMPTED CALL
# once when every retry is exhausted). RETRY_ATTEMPTS=0 disables retrying.
RETRY_ATTEMPTS = max(0, int(os.getenv("RAG_RETRY_ATTEMPTS", "2")))
RETRY_BACKOFF_S = max(0.0, float(os.getenv("RAG_RETRY_BACKOFF_S", "2.0")))

# Retrieval quality: how many paragraph chunks are handed to the model.
TOP_K = max(1, int(os.getenv("RAG_TOP_K", "4")))
# Question contract (mirrors ticket subject/description caps).
MAX_QUESTION_CHARS = int(os.getenv("RAG_MAX_QUESTION_CHARS", "500"))
# Unknown roles read no pools (same rule as the knowledge base itself).
