"""Local RAG core — semantic index and retrieval over the Library corpus.

Pure Python with a single isolated network touchpoint (`embedder.py`, which
calls Ollama). Everything else operates on injected ``embed_fn``/``make_llm_fn``
callables so the indexer/retriever/chat/condense layers stay unit-testable
without a running Ollama.

The Conversa is multi-turn (``PLANO_CONVERSA_MULTITURNO.md``, jul/2026):
``condense.py`` rewrites a follow-up question as standalone from the last 1-2
turns before it reaches ``retriever.retrieve``, whose own candidate pool is
then diversified by MMR so near-duplicate sibling chunks stop crowding out
the rest of the context — see the module docstrings for both.

The layer reuses the project's existing infrastructure — ``llm_factory.make_llm``
for provider routing (Ollama/Gemini), ``llm_utils.split_text`` for chunking, and
the Library scanner (``scan_library``) as the corpus source — instead of growing a
second way of talking to an LLM. Torch-free: embeddings run on Ollama (llama.cpp),
the vector store is a thin numpy wrapper, no FAISS/Chroma.

The embedding space is versioned (``embed_space_id`` in ``rag.stats``, folded from
the embed model, the vector width and the indexer's content scheme — task-instruction
prefixes, contextual chunk headers, PDF-noise cleanup). Anything that changes what
gets embedded requires a reindex and must bump the scheme marker in
``core/rag/indexer.py`` — see ``PLANO_RAG_ESPACO_EMBEDDING`` in ``docs/HISTORY.md``.
"""
