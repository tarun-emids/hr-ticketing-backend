"""HR assistant (RAG over the knowledge base) — one app, one file per concern.

    settings.py    env knobs (Gemini API key, model/endpoint URLs, top-k)
    chunking.py    pure rules: knowledge-block -> citable paragraph chunks
    embeddings.py  Google Gemini embeddings client + cosine search
    llm.py         Google Gemini chat-completions client (behind its breaker)
    repository.py  SQL persistence: chunk store + assistant_queries audit rows
    service.py     orchestration: retrieve -> prompt -> cite -> persist
    controller.py  the HTTP face (POST /api/assistant/ask)

Every answer is grounded in knowledge-base paragraphs and MUST carry inline
citations in the form [REF ¶block] (e.g. [KB-E-01 ¶12]); the service parses
them back to the exact chunks and also appends a machine-verified sources
footer, so the citation promise never depends on model goodwill alone.
"""
