"""Cross-module ML observability — the Observatório hub's core (pure).

Five read-only modules, mirroring ``core/recipes/history.py`` and
``core/rag/analytics.py``: ``activity.py`` is the append-only cross-module log
of successful ML operations; ``logs.py`` is its failure-log counterpart,
written from the GUI's ``EventBus`` broadcast point; ``model_timing.py`` logs
per-``(domain, model)`` latency; ``disk_usage.py`` scans ``~/.mill-tools/``
for what every store is spending on disk; ``status.py`` is a read-only
aggregator of what already exists elsewhere (gates, classifier label counts,
hardcoded thresholds, model timings) into a single snapshot. None of them
compute anything new — this package is purely observational.
"""
