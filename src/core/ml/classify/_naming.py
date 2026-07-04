"""Domain constants + on-disk naming helpers shared across the classify/ package.

Split out so ``prototypes.py``/``labels.py``/``inference.py`` don't need to
import each other just to resolve a domain's file names. The original, still
-default domain (transcription analysis profiles) keeps its pre-existing
filenames (no ``"transcription_profile_"`` prefix) — this package split
invalidates nothing on disk, same contract as before the split.
"""

from __future__ import annotations

# The original, still-default domain: transcription analysis profiles. Its
# filenames are the pre-existing ones (no "transcription_profile_" prefix) so
# upgrading to multi-domain classification invalidates nothing on disk.
DOMAIN_TRANSCRIPTION_PROFILE = "transcription_profile"
# Tier A domains (docs/plans/implemented/PLANO_ML_NOVAS_FEATURES.md, item 3.4).
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
