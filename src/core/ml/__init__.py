"""Classic ML foundation — mirrors ``core/rag`` (gate, injection, versioned cache).

The package is split into two layers by dependency weight:

* **numpy-pure foundation** (``features``, ``dedup``, ``types``) — reuses the
  persisted RAG ``VectorStore`` to expose document-level matrices and a
  similarity dedup, with no dependency beyond numpy (already a base dependency).
  This is the "free foundation": real value (deduplication) without any new
  ``pip install``.
* **scikit-learn layer** (``deps``, ``store``) — the gate (``is_available``) and
  the versioned model persistence the future semantic/tabular waves (Plans 4/5)
  will use. Only the *algorithms* require the ``[ml]`` extra; the accessor above
  does not.

Nothing here imports Flet, DuckDB or touches the network; scikit-learn/joblib are
imported lazily so app start stays fast.
"""
