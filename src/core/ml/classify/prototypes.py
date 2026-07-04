"""Zero-shot prototypes: one embedding per class, cached by domain + class-set hash.

Each profile/class becomes a *prototype*: a short canonical text (``label`` +
``source_hint``, or a hand-written seed for the Tier A domains) embedded once
by the same model as the documents, then L2-normalized. A document is
classified by the nearest prototype (max cosine over
``features.document_matrix``) — zero labels, zero training, works from the
first use. Prototypes are cached on disk keyed by a hash of the profile set,
so the embedder is only called when that set changes.

Split out of the former ``classify.py`` (471 lines > the architecture's ~400
ceiling); labels+training live in ``labels.py``, dispatch in ``inference.py``.
See ``classify/__init__.py`` for the still-flat public API.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np

from src.core.io_atomic import write_group
from src.core.ml.classify._naming import (
    DOMAIN_DATA,
    DOMAIN_DOCUMENT,
    DOMAIN_TRANSCRIPTION_PROFILE,
    _PROTO_JSON,
    _PROTO_NPZ,
    _proto_filenames,
)
from src.core.ml.store import model_dir
from src.core.ml.types import Classification

# Prototype seeds for the two new domains — (class_id, prototype_text) pairs,
# same shape as _profile_seeds()'s output. Small, hand-written catalogs (no
# existing registry to derive them from, unlike the transcription profiles).
_DATA_DOMAIN_SEEDS: list[tuple[str, str]] = [
    (
        "financial",
        "Financial data. Revenue, expenses, invoices, transactions, budgets.",
    ),
    (
        "research",
        "Scientific or research data. Experiment results, measurements, surveys.",
    ),
    (
        "log",
        "Operational log data. Timestamped events, system logs, application traces.",
    ),
    (
        "people",
        "People or registry data. Names, contacts, employee or customer records.",
    ),
    ("catalog", "Product catalog data. Items, SKUs, prices, inventory."),
]

_DOCUMENT_TYPE_SEEDS: list[tuple[str, str]] = [
    (
        "invoice",
        "Invoice or receipt. Billed amounts, taxes, payment terms, itemized charges.",
    ),
    (
        "minutes",
        "Meeting minutes. Attendees, decisions, action items, discussion notes.",
    ),
    (
        "article",
        "Article or report. Analysis, findings, structured sections, references.",
    ),
    (
        "contract",
        "Contract or agreement. Parties, clauses, terms, signatures, obligations.",
    ),
    (
        "correspondence",
        "Correspondence. Letter or formal written communication between parties.",
    ),
]


def _profile_seeds() -> list[tuple[str, str]]:
    """Return ``(profile_id, prototype_text)`` for every analysis profile.

    The prototype text is derived from the profile's own ``label`` and
    ``source_hint`` so the taxonomy stays in sync with ``src/analysis`` — no new
    catalog to maintain. Order follows the profile registry.
    """
    from src.analysis.profiles import PROFILES

    return [(p.id, f"{p.label}. {p.source_hint}.") for p in PROFILES.values()]


def _seeds_for_domain(domain: str) -> list[tuple[str, str]]:
    """Dispatch to the prototype seeds for ``domain``.

    Raises:
        ValueError: for an unregistered domain — callers pass a constant, so
            this only fires on a genuine typo/programming error.
    """
    if domain == DOMAIN_TRANSCRIPTION_PROFILE:
        return _profile_seeds()
    if domain == DOMAIN_DATA:
        return _DATA_DOMAIN_SEEDS
    if domain == DOMAIN_DOCUMENT:
        return _DOCUMENT_TYPE_SEEDS
    raise ValueError(f"Unknown classification domain: {domain!r}")


def _seeds_signature(seeds: list[tuple[str, str]], embed_space_id: str) -> str:
    """Stable hash of the profile set + embedding space.

    Changes when ids/texts change *or* when ``embed_space_id`` changes
    (model/dim, from ``rag.stats.embed_space_id``) — a cached prototype
    matrix embedded in one model's space is meaningless cosine-compared
    against document vectors from a different one; without this, switching
    the embed model and reindexing left stale prototypes valid and
    predicting garbage in silence (M2).
    """
    payload = f"{embed_space_id}\n" + "\n".join(f"{pid}\t{text}" for pid, text in seeds)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _save_prototypes(
    directory: Path,
    P: np.ndarray,
    ids: list[str],
    signature: str,
    *,
    npz_name: str = _PROTO_NPZ,
    json_name: str = _PROTO_JSON,
) -> None:
    """Persist the prototype matrix + ids + signature (npz/json, no pickle),
    as one atomic unit (:func:`src.core.io_atomic.write_group`)."""
    npz_buf = io.BytesIO()
    np.savez_compressed(npz_buf, P=P)
    json_bytes = json.dumps(
        {"ids": ids, "signature": signature}, ensure_ascii=False
    ).encode("utf-8")
    write_group(
        [
            (directory / npz_name, npz_buf.getvalue()),
            (directory / json_name, json_bytes),
        ]
    )


def _load_prototypes(
    directory: Path,
    signature: str,
    *,
    npz_name: str = _PROTO_NPZ,
    json_name: str = _PROTO_JSON,
) -> tuple[np.ndarray, list[str]] | None:
    """Load cached prototypes only if their signature still matches the profiles.

    A corrupt ``.npz`` (``zipfile.BadZipFile``) or one missing the expected
    key is treated the same as any other cache miss — same parity as
    ``ml.cache.load_map``.
    """
    npz_path = directory / npz_name
    json_path = directory / json_name
    if not (npz_path.exists() and json_path.exists()):
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if payload.get("signature") != signature:
            return None
        P = np.load(npz_path)["P"]
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None
    return P, payload["ids"]


def profile_prototypes(
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    *,
    cache_dir: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
    embed_space_id: str = "?",
) -> tuple[np.ndarray, list[str]]:
    """Return the L2-normalized prototype matrix ``(C, D)`` and its class ids.

    Reads the on-disk cache when ``domain``'s class set *and* embedding space
    are unchanged (no embedder needed); otherwise embeds one canonical text
    per class via ``embed_fn`` (one call, then cached). Raises ``RuntimeError``
    on a cache miss without an ``embed_fn`` so the caller can surface the
    embedder setup hint.

    Args:
        embed_fn: Embeds the seed texts on a cache miss.
        cache_dir: Where the prototype cache lives (default ``model_dir()``).
        domain: Which class set to use.
        embed_space_id: Identifies the RAG's current embedding space (model +
            dim, from ``rag.stats.embed_space_id``) — folded into the cache
            signature so switching the embed model invalidates stale
            prototypes instead of silently comparing vectors from a different
            space. Defaults to ``"?"`` for callers that don't track it
            explicitly (the classify() call chain always does — see
            ``inference.py``).
    """
    cache_dir = cache_dir or model_dir()
    seeds = _seeds_for_domain(domain)
    signature = _seeds_signature(seeds, embed_space_id)
    npz_name, json_name = _proto_filenames(domain)

    cached = _load_prototypes(
        cache_dir, signature, npz_name=npz_name, json_name=json_name
    )
    if cached is not None:
        return cached

    if embed_fn is None:
        raise RuntimeError("Prototypes not cached and no embedder provided.")

    ids = [pid for pid, _ in seeds]
    P = np.asarray(embed_fn([text for _, text in seeds]), dtype=np.float32)
    P = (P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-8)).astype(np.float32)
    _save_prototypes(
        cache_dir, P, ids, signature, npz_name=npz_name, json_name=json_name
    )
    return P, ids


def classify_zeroshot(
    doc_vec: np.ndarray, P: np.ndarray, ids: list[str]
) -> Classification:
    """Nearest-prototype classification over L2-normalized vectors.

    ``argmax cos(doc_vec, P)``; ``margin`` is top-1 minus top-2 cosine (the
    uncertainty signal). ``doc_vec`` is re-normalized defensively even though the
    accessor already returns unit vectors.
    """
    v = np.asarray(doc_vec, dtype=np.float32)
    v = v / (np.linalg.norm(v) + 1e-8)
    sims = P @ v
    order = np.argsort(sims)[::-1]
    top = int(order[0])
    confidence = float(sims[top])
    margin = float(sims[order[0]] - sims[order[1]]) if len(order) > 1 else confidence
    return Classification(ids[top], confidence, margin, "zeroshot")
