"""scikit-learn availability gate — mirrors ``rag.embedder.is_available()``.

The numpy-pure foundation (``features``/``dedup``) does *not* gate here. Only the
algorithm layer (classification/clustering/regression of Plans 4/5) imports
scikit-learn, so only those flows call ``is_available()``; when it returns False
the caller shows ``SETUP_HINT`` instead of failing mid-pipeline.
"""

from __future__ import annotations

SETUP_HINT = "Instale o extra de ML: uv sync --extra ml"
UMAP_SETUP_HINT = "Instale o extra de visualização ML: uv sync --extra ml-viz"


def is_available() -> bool:
    """True if scikit-learn can be imported (the ``[ml]`` extra is installed).

    The import is lazy (only at call time), so app start never pays for it.
    """
    try:
        import sklearn  # noqa: F401  (presence probe only)

        return True
    except ImportError:
        return False


def umap_available() -> bool:
    """True if umap-learn can be imported (the optional ``[ml-viz]`` extra).

    Gates only the UMAP projection; PCA (the default) needs just ``[ml]``.
    """
    try:
        import umap  # noqa: F401  (presence probe only)

        return True
    except ImportError:
        return False
