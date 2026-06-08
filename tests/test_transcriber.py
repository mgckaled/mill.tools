import pytest


# ── format_elapsed ───────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("seconds, expected", [
    (0,      "0s"),
    (5,      "5s"),
    (59,     "59s"),
    (60,     "1m 00s"),
    (90,     "1m 30s"),
    (3600,   "1h 00m 00s"),
    (3661,   "1h 01m 01s"),
    (7384,   "2h 03m 04s"),
])
def test_format_elapsed(seconds, expected):
    from src.transcriber import format_elapsed
    assert format_elapsed(seconds) == expected


# ── _resolve_device ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_resolve_device_cuda_fallback(mocker):
    """Se ctranslate2 lança RuntimeError, deve retornar CPU."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        side_effect=RuntimeError("no CUDA"),
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cpu"
    assert compute == "int8"


@pytest.mark.unit
def test_resolve_device_cuda_int8_float32(mocker):
    """Se int8_float32 disponível em CUDA, deve preferir CUDA."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["int8_float32", "float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "int8_float32"


@pytest.mark.unit
def test_resolve_device_cuda_float32_fallback(mocker):
    """Se apenas float32 disponível em CUDA, usa float32."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "float32"
