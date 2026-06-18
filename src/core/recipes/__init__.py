"""Linear, cross-module automation recipes (PR8).

A recipe is an ordered chain of steps where each step's output feeds the next,
crossing module boundaries (e.g. ``URL → download audio → normalize → transcribe
→ analyze``). The package is pure core: adapters wrap existing pure functions in
``src/core`` and never touch the GUI workers, so it stays reusable by both the
CLI and the GUI.
"""
