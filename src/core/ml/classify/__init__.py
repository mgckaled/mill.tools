"""Zero-shot/supervised text classification — reusable across domains.

The class set is **not** invented here: for the default domain
(``transcription_profile``) it is exactly the analysis profiles the app already
exposes via ``--profile`` (``src/analysis/profiles/``). The same
prototype+cosine+upgrade infrastructure is reused, keyed by ``domain``, for two
more domains added in Tier A of ``docs/plans/implemented/PLANO_ML_NOVAS_FEATURES.md``:
``data_domain`` (financial/research/log/people/catalog, for Dados) and
``document_type`` (invoice/minutes/article/contract/correspondence, for
Documentos). Every public function defaults ``domain=DOMAIN_TRANSCRIPTION_PROFILE``
and derives filenames that match the pre-existing on-disk names for that one
domain exactly (``profile_prototypes.npz``/``profile_classifier``/etc.) — no
cache/model invalidation for the original use case. Two regimes, chosen
automatically:

* **Zero-shot (cold start).** See ``prototypes.py``: each class becomes a short
  canonical text embedded once, then nearest-prototype cosine classifies a
  document. Zero labels, zero training — works from the first use.

* **Supervised (upgrade).** See ``labels.py``: recorded labels are joined with
  the document vectors and, once there are enough per class, a calibrated
  linear model is trained and persisted. Until then the zero-shot path stands.

``inference.py`` ties the two together: ``classify()`` dispatches to whichever
regime currently applies. numpy-pure except the supervised trainer (gated by
the ``[ml]`` extra) — document vectors are already pooled + L2-normalized by
the accessor, so linear models and cosine both operate on the unit sphere.

This package is a 3-way split of what used to be a single 471-line
``classify.py`` (architecture's ~400-line ceiling for a ``core/`` module) —
every name below is re-exported unchanged so no call site outside this
package needed to change.
"""

from __future__ import annotations

from src.core.ml.classify._naming import DOMAIN_DATA as DOMAIN_DATA
from src.core.ml.classify._naming import DOMAIN_DOCUMENT as DOMAIN_DOCUMENT
from src.core.ml.classify._naming import (
    DOMAIN_TRANSCRIPTION_PROFILE as DOMAIN_TRANSCRIPTION_PROFILE,
)
from src.core.ml.classify._naming import MIN_PER_CLASS as MIN_PER_CLASS
from src.core.ml.classify._naming import _labels_json_name as _labels_json_name
from src.core.ml.classify._naming import _LABELS_JSON as _LABELS_JSON
from src.core.ml.classify._naming import _model_name as _model_name
from src.core.ml.classify._naming import _MODEL_NAME as _MODEL_NAME
from src.core.ml.classify._naming import _proto_filenames as _proto_filenames
from src.core.ml.classify._naming import _PROTO_JSON as _PROTO_JSON
from src.core.ml.classify._naming import _PROTO_NPZ as _PROTO_NPZ
from src.core.ml.classify.inference import classify as classify
from src.core.ml.classify.inference import (
    has_supervised_model as has_supervised_model,
)
from src.core.ml.classify.labels import _labels_file as _labels_file
from src.core.ml.classify.labels import _training_xy as _training_xy
from src.core.ml.classify.labels import domain_label_count as domain_label_count
from src.core.ml.classify.labels import labels_signature as labels_signature
from src.core.ml.classify.labels import load_labels as load_labels
from src.core.ml.classify.labels import maybe_train as maybe_train
from src.core.ml.classify.labels import model_signature as model_signature
from src.core.ml.classify.labels import record_label as record_label
from src.core.ml.classify.labels import train_supervised as train_supervised
from src.core.ml.classify.prototypes import _load_prototypes as _load_prototypes
from src.core.ml.classify.prototypes import _profile_seeds as _profile_seeds
from src.core.ml.classify.prototypes import _save_prototypes as _save_prototypes
from src.core.ml.classify.prototypes import _seeds_for_domain as _seeds_for_domain
from src.core.ml.classify.prototypes import _seeds_signature as _seeds_signature
from src.core.ml.classify.prototypes import classify_zeroshot as classify_zeroshot
from src.core.ml.classify.prototypes import profile_prototypes as profile_prototypes

__all__ = [
    "DOMAIN_DATA",
    "DOMAIN_DOCUMENT",
    "DOMAIN_TRANSCRIPTION_PROFILE",
    "MIN_PER_CLASS",
    "classify",
    "classify_zeroshot",
    "domain_label_count",
    "has_supervised_model",
    "labels_signature",
    "load_labels",
    "maybe_train",
    "model_signature",
    "profile_prototypes",
    "record_label",
    "train_supervised",
]
