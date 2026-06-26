"""Per-tab builders for the Data module's right panel.

Each ``build_*_tab(ctx)`` returns an object exposing the tab's root ``view`` plus
the event handlers the central router in ``view.py`` dispatches to. Shared state
and pure helpers live in ``src/gui/modules/data/_state.py``.
"""
