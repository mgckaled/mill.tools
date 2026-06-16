"""Local RAG core — semantic index and retrieval over the Library corpus.

Pure Python with a single isolated network touchpoint (`embedder.py`, which
calls Ollama). Everything else operates on injected ``embed_fn`` callables so
the indexer/retriever/chat layers stay unit-testable without a running Ollama.

The layer reuses the project's existing infrastructure — ``llm_factory.make_llm``
for provider routing (Ollama/Gemini), ``llm_utils.split_text`` for chunking, and
the Library scanner (``scan_library``) as the corpus source — instead of growing a
second way of talking to an LLM. Torch-free: embeddings run on Ollama (llama.cpp),
the vector store is a thin numpy wrapper, no FAISS/Chroma.
"""
