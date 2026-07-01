"""Cross-module ML observability — the Observatório hub's core (pure).

Two responsibilities, mirroring ``core/recipes/history.py`` and
``core/rag/analytics.py``: ``activity.py`` is the append-only cross-module log
every ML-touching operation writes to; ``status.py`` is a read-only aggregator
of what already exists elsewhere (gates, classifier label counts, hardcoded
thresholds, model timings) into a single snapshot. Neither computes anything
new — this package is purely observational.
"""
