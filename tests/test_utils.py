import pytest
from src.utils import sanitize_filename


# ── sanitize_filename ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "title, expected",
    [
        # Section separators → hyphen
        ("Título | Parte 2", "Título-Parte_2"),
        ("Título · Parte 2", "Título-Parte_2"),
        ("Título – Parte 2", "Título-Parte_2"),
        ("Título — Parte 2", "Título-Parte_2"),
        # Wide colon
        ("Python：Tutorial", "Python-Tutorial"),
        # ASCII colon — must not be dropped outright (NTFS ADS risk); same
        # treatment as the wide colon.
        ("Python: aula 1", "Python-aula_1"),
        ("a:b", "a-b"),
        # Invalid Windows chars
        ('arquivo<>bad"name', "arquivobadname"),
        ("path/with\\slash", "pathwithslash"),
        ("name?with*wildcards", "namewithwildcards"),
        # Exclamation/question punctuation
        ("Título incrível!", "Título_incrível"),
        ("Como funciona？", "Como_funciona"),
        # Spaces → underscore (multiple spaces collapse into single _ via \s+)
        ("palavra com espaço", "palavra_com_espaço"),
        ("  espaço  nas  bordas  ", "espaço_nas_bordas"),
        # Accents preserved (NTFS supports them)
        ("Programação Orientada", "Programação_Orientada"),
        # Hyphens with surrounding space → plain hyphen
        ("A - B - C", "A-B-C"),
        # Multiple underscores / hyphens collapsed
        ("a___b", "a_b"),
        ("a---b", "a-b"),
        # Empty after sanitisation
        ("!!!", ""),
        # Dot is NOT in _SANITIZE_INVALID — preserved
        ("Python 3.13 Tutorial", "Python_3.13_Tutorial"),
    ],
)
def test_sanitize_filename_parametrize(title, expected):
    assert sanitize_filename(title) == expected


@pytest.mark.unit
def test_sanitize_filename_strip_leading_trailing():
    """Result never starts or ends with '-', '_' or '.'."""
    result = sanitize_filename("  - título -  ")
    assert not result.startswith(("-", "_", "."))
    assert not result.endswith(("-", "_", "."))


@pytest.mark.unit
def test_sanitize_filename_caps_length_against_max_path():
    from src.utils import _MAX_STEM_LENGTH

    result = sanitize_filename("palavra " * 100)
    assert len(result) <= _MAX_STEM_LENGTH


@pytest.mark.unit
def test_sanitize_filename_truncation_does_not_leave_trailing_separator():
    from src.utils import _MAX_STEM_LENGTH

    # Construct a title whose sanitized form has a separator exactly at the
    # truncation boundary, so the naive slice would end in "_" or "-".
    long_word = "a" * (_MAX_STEM_LENGTH - 1)
    result = sanitize_filename(f"{long_word} resto do título")
    assert not result.endswith(("-", "_", "."))
