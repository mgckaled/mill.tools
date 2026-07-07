"""Textual NLP engines — keyphrases, extractive summary, named entities.

Pure ``str in → structure out`` functions, independent of ``core/ml`` (which is
embedding geometry). Each engine reads the *whole document* (document reading,
distinct from the RAG's chunk retrieval), is deterministic, and degrades on its
own: keyphrases/entities gate their optional dependency via ``is_available()``;
the extractive summary is self-contained on the ``[ml]`` TfidfVectorizer.

The Plan 4C "ficha de leitura" only *composes* these engines — they live here so
there is no duplication later.

``nl2cli.py`` (PLANO_NL2CLI_HUB_IA.md) is the odd one out — an LLM generation
task, not classic NLP — but mirrors ``core/data/nl2sql.py``'s shape closely
enough (PT question → strict-JSON payload via an injected ``make_llm_fn``)
that it lives beside the rest of the text-generation core rather than opening
a new package for one file.
"""
