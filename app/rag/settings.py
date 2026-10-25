"""Assistant env configuration (reads app/config's already-loaded .env).

Every knob is env-tunable without a deploy. `RAG_HF_TOKEN` is the master
switch: when it is empty the assistant answers with a configuration notice
instead of calling the network (and seeding skips chunk embedding), so the
feature is fully optional in every environment.
"""

import os

# --- Hugging Face Inference Providers (free tier: create a token at
# huggingface.co/settings/tokens with "Inference" permissions) ---------------
HF_TOKEN = os.getenv("RAG_HF_TOKEN", "").strip() or os.getenv(
    "HF_TOKEN", ""
).strip()

# Chat: OpenAI-compatible endpoint (HF router). Any chat model the token can
# serve works — if you get 404/403, pick another enabled model on
# https://huggingface.co/models?inference_provider=all&sort=trending
# and set RAG_CHAT_MODEL.
CHAT_URL = os.getenv(
    "RAG_CHAT_URL", "https://router.huggingface.co/v1/chat/completions"
)
CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
CHAT_TIMEOUT_S = float(os.getenv("RAG_CHAT_TIMEOUT_S", "60"))
CHAT_MAX_TOKENS = int(os.getenv("RAG_CHAT_MAX_TOKENS", "512"))

# Embeddings: the sentence-transformers feature-extraction pipeline. The model
# name is part of the URL shape on HF's router, so the whole URL is env-tunable.
EMBED_URL = os.getenv(
    "RAG_EMBED_URL",
    "https://router.huggingface.co/hf-inference/models/"
    "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction",
)
EMBED_TIMEOUT_S = float(os.getenv("RAG_EMBED_TIMEOUT_S", "20"))
# Providers cap batch sizes; smaller batches also ride free-tier rate limits.
EMBED_BATCH = int(os.getenv("RAG_EMBED_BATCH", "32"))

# Retrieval quality: how many paragraph chunks are handed to the model.
TOP_K = max(1, int(os.getenv("RAG_TOP_K", "4")))
# Question contract (mirrors ticket subject/description caps).
MAX_QUESTION_CHARS = int(os.getenv("RAG_MAX_QUESTION_CHARS", "500"))
# Unknown roles read no pools (same rule as the knowledge base itself).
