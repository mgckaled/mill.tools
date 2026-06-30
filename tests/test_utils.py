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
