"""Zero-shot/supervised text classification — reusable across domains.

The class set is **not** invented here: for the default domain
(``transcription_profile``) it is exactly the analysis profiles the app already
exposes via ``--profile`` (``src/analysis/profiles/``). The same
prototype+cosine+upgrade infrastructure is reused, keyed by ``domain``, for two
more domains added in Tier A of ``docs/plan/PLANO_ML_NOVAS_FEATURES.md``:
``data_domain`` (financial/research/log/people/catalog, for Dados) and
``document_type`` (invoice/minutes/article/contract/correspondence, for
Documentos). Every public function defaults ``domain=DOMAIN_TRANSCRIPTION_PROFILE``
and derives filenames that match the pre-existing on-disk names for that one
domain exactly (``profile_prototypes.npz``/``profile_classifier``/etc.) — no
cache/model invalidation for the original use case. Two regimes, chosen
automatically:

* **Zero-shot (cold start).** Each profile becomes a *prototype*: a short
  canonical text (``label`` + ``source_hint``) embedded once by the same model as
  the documents, then L2-normalized. A document is classified by the nearest
  prototype (max cosine over ``features.document_matrix``). Zero labels, zero
  training — works from the first use. The prototypes are cached on disk keyed by
  a hash of the profile set, so the embedder is only called when that set changes.

* **Supervised (upgrade).** The user already picks ``--profile`` on every run —
  that choice is a gold label. Recorded labels (``record_label``) are joined with
  the document vectors and, once there are enough per class, a calibrated linear
  model (``LinearSVC`` + ``CalibratedClassifierCV``) is trained over ``dm.X`` and
  persisted via the versioned ``ml.store``. Until then the zero-shot path stands.

numpy-pure except the supervised trainer (gated by the ``[ml]`` extra). The
document vectors are already pooled + L2-normalized by the accessor, so linear
models and cosine both operate on the unit sphere.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np

from src.core.ml.store import load_model, model_dir, save_model
from src.core.ml.types import Classification

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix

# The original, still-default domain: transcription analysis profiles. Its
# filenames are the pre-existing ones (no "transcription_profile_" prefix) so
# upgrading to multi-domain classification invalidates nothing on disk.
DOMAIN_TRANSCRIPTION_PROFILE = "transcription_profile"
# Tier A domains (docs/plan/PLANO_ML_NOVAS_FEATURES.md, item 3.4).
DOMAIN_DATA = "data_domain"
DOMAIN_DOCUMENT = "document_type"

_PROTO_NPZ = "profile_prototypes.npz"
_PROTO_JSON = "profile_prototypes.json"
_MODEL_NAME = "profile_classifier"
_LABELS_JSON = "profile_labels.json"

# Minimum labelled documents *per class* before the supervised model is trained;
# below this the zero-shot prototype path stands. Two is the floor that lets a
# 2-fold stratified split run during probability calibration.
MIN_PER_CLASS = 2

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


# ---------------------------------------------------------------------------
# Prototypes — one embedding per class (cached by domain + class-set hash).
# ---------------------------------------------------------------------------


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


def _proto_filenames(domain: str) -> tuple[str, str]:
    """Return ``(npz_name, json_name)`` for ``domain``'s prototype cache."""
    if domain == DOMAIN_TRANSCRIPTION_PROFILE:
        return _PROTO_NPZ, _PROTO_JSON
    return f"{domain}_prototypes.npz", f"{domain}_prototypes.json"


def _model_name(domain: str) -> str:
    """Return the ``ml.store`` model name for ``domain``'s supervised classifier."""
    return (
        _MODEL_NAME
        if domain == DOMAIN_TRANSCRIPTION_PROFILE
        else f"{domain}_classifier"
    )


def _labels_json_name(domain: str) -> str:
    """Return the gold-labels filename for ``domain``."""
    return (
        _LABELS_JSON
        if domain == DOMAIN_TRANSCRIPTION_PROFILE
        else f"{domain}_labels.json"
    )


def _seeds_signature(seeds: list[tuple[str, str]]) -> str:
    """Stable hash of the profile set — changes only when ids/texts change."""
    payload = "\n".join(f"{pid}\t{text}" for pid, text in seeds)
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
    """Persist the prototype matrix + ids + signature (npz/json, no pickle)."""
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / npz_name, P=P)
    (directory / json_name).write_text(
        json.dumps({"ids": ids, "signature": signature}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_prototypes(
    directory: Path,
    signature: str,
    *,
    npz_name: str = _PROTO_NPZ,
    json_name: str = _PROTO_JSON,
) -> tuple[np.ndarray, list[str]] | None:
    """Load cached prototypes only if their signature still matches the profiles."""
    npz_path = directory / npz_name
    json_path = directory / json_name
    if not (npz_path.exists() and json_path.exists()):
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if payload.get("signature") != signature:
            return None
        P = np.load(npz_path)["P"]
    except (OSError, ValueError, KeyError):
        return None
    return P, payload["ids"]


def profile_prototypes(
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    *,
    cache_dir: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
) -> tuple[np.ndarray, list[str]]:
    """Return the L2-normalized prototype matrix ``(C, D)`` and its class ids.

    Reads the on-disk cache when ``domain``'s class set is unchanged (no
    embedder needed); otherwise embeds one canonical text per class via
    ``embed_fn`` (one call, then cached). Raises ``RuntimeError`` on a cache
    miss without an ``embed_fn`` so the caller can surface the embedder setup
    hint.
    """
    cache_dir = cache_dir or model_dir()
    seeds = _seeds_for_domain(domain)
    signature = _seeds_signature(seeds)
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


# ---------------------------------------------------------------------------
# Supervised upgrade — labels recorded from the user's profile confirmations.
# ---------------------------------------------------------------------------


def _labels_file(
    directory: Path | None = None, *, domain: str = DOMAIN_TRANSCRIPTION_PROFILE
) -> Path:
    """Return the on-disk gold-label store (``~/.mill-tools/ml/profile_labels.json``)."""
    return (directory or model_dir()) / _labels_json_name(domain)


def load_labels(
    *, directory: Path | None = None, domain: str = DOMAIN_TRANSCRIPTION_PROFILE
) -> dict[str, str]:
    """Return the ``{source_path: class_id}`` gold labels, tolerating absence."""
    try:
        data = json.loads(
            _labels_file(directory, domain=domain).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_label(
    source_path: str,
    profile_id: str,
    *,
    directory: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
) -> None:
    """Record the user's confirmed/corrected class for a document.

    This is the only labelling step — it piggybacks on the choice the user
    already makes, so there is no dedicated annotation chore. A later
    ``maybe_train`` turns enough of these into a supervised model.
    """
    path = str(Path(source_path).resolve())
    labels = load_labels(directory=directory, domain=domain)
    labels[path] = profile_id
    out = _labels_file(directory, domain=domain)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logging.debug("[d] Could not write %s labels: %s", domain, exc)


def labels_signature(labels: dict[str, str]) -> str:
    """Stable hash of the label set — invalidates the trained model when it changes."""
    payload = "\n".join(f"{p}\t{labels[p]}" for p in sorted(labels))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _training_xy(
    dm: DocumentMatrix, labels: dict[str, str]
) -> tuple[np.ndarray, list[str]]:
    """Join document vectors with gold labels into ``(X, y)`` for training."""
    rows: list[int] = []
    y: list[str] = []
    for i, source in enumerate(dm.source_paths):
        if source in labels:
            rows.append(i)
            y.append(labels[source])
    X = dm.X[rows] if rows else np.empty((0, dm.X.shape[1]), dtype=np.float32)
    return X, y


def train_supervised(
    dm: DocumentMatrix,
    labels: dict[str, str],
    *,
    signature: str | None = None,
    directory: Path | None = None,
    min_per_class: int = MIN_PER_CLASS,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
):
    """Train + persist a calibrated linear classifier; return it, or ``None``.

    Returns ``None`` (so the caller stays on zero-shot) when there are fewer than
    two classes or any class has fewer than ``min_per_class`` labelled documents.
    Otherwise fits ``LinearSVC(class_weight="balanced")`` wrapped in
    ``CalibratedClassifierCV`` (sigmoid — robust for the small label counts here)
    over ``dm.X`` and saves it via the versioned ``ml.store``.

    Raises:
        RuntimeError: if the ``[ml]`` extra (scikit-learn) is not installed.
    """
    from src.core.ml.deps import SETUP_HINT, is_available

    if not is_available():
        raise RuntimeError(SETUP_HINT)

    from collections import Counter

    X, y = _training_xy(dm, labels)
    counts = Counter(y)
    if len(counts) < 2 or (counts and min(counts.values()) < min_per_class):
        return None

    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.svm import LinearSVC

    cv = min(5, min(counts.values()))
    base = LinearSVC(class_weight="balanced", dual="auto", random_state=0)
    model = CalibratedClassifierCV(base, method="sigmoid", cv=cv)
    model.fit(X, y)

    sig = signature if signature is not None else labels_signature(labels)
    save_model(model, _model_name(domain), signature=sig, directory=directory)
    return model


def maybe_train(
    dm: DocumentMatrix,
    *,
    directory: Path | None = None,
    min_per_class: int = MIN_PER_CLASS,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
):
    """Train from the recorded labels if enough have accumulated; else ``None``."""
    labels = load_labels(directory=directory, domain=domain)
    if not labels:
        return None
    return train_supervised(
        dm, labels, directory=directory, min_per_class=min_per_class, domain=domain
    )


def classify(
    doc_vec: np.ndarray,
    *,
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    dm: DocumentMatrix | None = None,  # noqa: ARG001 — reserved for future routing
    directory: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
) -> Classification:
    """Classify ``doc_vec`` within ``domain``: trained model if available + valid,
    else zero-shot.

    The supervised model is used only when ``ml.store`` holds one whose signature
    still matches the current label set; any mismatch (labels changed or sklearn
    upgraded) transparently falls back to the zero-shot prototypes. Passing a
    non-default ``domain`` (``DOMAIN_DATA``/``DOMAIN_DOCUMENT``) reuses this exact
    infrastructure for a different class set — see the module docstring.
    """
    labels = load_labels(directory=directory, domain=domain)
    if labels:
        model = load_model(
            _model_name(domain),
            signature=labels_signature(labels),
            directory=directory,
        )
        if model is not None:
            proba = model.predict_proba(
                np.asarray(doc_vec, dtype=np.float32).reshape(1, -1)
            )[0]
            order = np.argsort(proba)[::-1]
            classes = model.classes_
            confidence = float(proba[order[0]])
            margin = (
                float(proba[order[0]] - proba[order[1]])
                if len(order) > 1
                else confidence
            )
            return Classification(
                str(classes[order[0]]), confidence, margin, "supervised"
            )

    P, ids = profile_prototypes(embed_fn, cache_dir=directory, domain=domain)
    return classify_zeroshot(doc_vec, P, ids)


def domain_label_count(
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE, *, directory: Path | None = None
) -> int:
    """Number of gold labels recorded for ``domain`` — used by the Observatório
    status board (item 3.5) to show classifier health without exposing the
    on-disk filename scheme."""
    return len(load_labels(directory=directory, domain=domain))


def has_supervised_model(
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE, *, directory: Path | None = None
) -> bool:
    """True if ``domain`` currently has a valid trained model in use (not just
    labels recorded) — i.e. ``classify()`` would take the supervised branch."""
    labels = load_labels(directory=directory, domain=domain)
    if not labels:
        return False
    model = load_model(
        _model_name(domain), signature=labels_signature(labels), directory=directory
    )
    return model is not None
