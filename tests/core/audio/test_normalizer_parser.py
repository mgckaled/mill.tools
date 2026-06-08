import pytest
from src.core.audio.normalizer import _parse_loudnorm_json


_REAL_STDERR = """\
[Parsed_loudnorm_0 @ 0x...] Input Integrated:    -18.3 LUFS
{
    "input_i" : "-18.27",
    "input_tp" : "-3.21",
    "input_lra" : "8.10",
    "input_thresh" : "-28.36",
    "output_i" : "-14.00",
    "output_tp" : "-1.15",
    "output_lra" : "7.95",
    "output_thresh" : "-24.09",
    "normalization_type" : "dynamic",
    "target_offset" : "0.15"
}
size=       0kB time=00:00:10.38 bitrate=   0.0kbits/s speed= 108x
"""


@pytest.mark.unit
def test_parse_loudnorm_json_valid():
    result = _parse_loudnorm_json(_REAL_STDERR)
    assert result is not None
    assert result["input_i"] == "-18.27"
    assert result["input_tp"] == "-3.21"
    assert result["target_offset"] == "0.15"


@pytest.mark.unit
def test_parse_loudnorm_json_all_keys_present():
    result = _parse_loudnorm_json(_REAL_STDERR)
    expected_keys = {
        "input_i", "input_tp", "input_lra", "input_thresh",
        "output_i", "output_tp", "output_lra", "output_thresh",
        "normalization_type", "target_offset",
    }
    assert expected_keys.issubset(result.keys())


@pytest.mark.unit
def test_parse_loudnorm_json_no_json_block():
    """stderr sem bloco JSON deve retornar None sem lançar exceção."""
    result = _parse_loudnorm_json("ffmpeg version 6.1\nSome other output\n")
    assert result is None


@pytest.mark.unit
def test_parse_loudnorm_json_empty_string():
    assert _parse_loudnorm_json("") is None


@pytest.mark.unit
def test_parse_loudnorm_json_malformed_json():
    stderr = "{\n  invalid_json_here\n}\n"
    result = _parse_loudnorm_json(stderr)
    assert result is None


@pytest.mark.unit
def test_parse_loudnorm_json_partial_block():
    """Bloco JSON abre mas não fecha — deve retornar None."""
    stderr = "{\n  \"input_i\": \"-18.27\"\n"  # sem fechar
    result = _parse_loudnorm_json(stderr)
    assert result is None
