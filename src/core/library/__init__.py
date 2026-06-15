"""Library core — a typed, filterable index over the project's output/ tree.

Pure Python (no Flet): scans the per-module output directories, classifies each
file by logical kind/category and exposes filter/sort helpers reused by the GUI
Library module and the optional `library` CLI subcommand.
"""
