import pytest
from src.utils import sanitize_filename, format_duration, extract_video_id, format_metadata


# ── sanitize_filename ────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("title, expected", [
    # Separadores de seção → hífen
    ("Título | Parte 2",           "Título-Parte_2"),
    ("Título · Parte 2",           "Título-Parte_2"),
    ("Título – Parte 2",           "Título-Parte_2"),
    ("Título — Parte 2",           "Título-Parte_2"),
    # Dois pontos largos
    ("Python：Tutorial",           "Python-Tutorial"),
    # Chars inválidos Windows
    ('arquivo<>bad"name',          "arquivobadname"),
    ("path/with\\slash",           "pathwithslash"),
    ("name?with*wildcards",        "namewithwildcards"),
    # Pontuação exclamação/interrogação
    ("Título incrível!",           "Título_incrível"),
    ("Como funciona？",             "Como_funciona"),
    # Espaços → underscore (múltiplos espaços colapsam em _único via \s+)
    ("palavra com espaço",         "palavra_com_espaço"),
    ("  espaço  nas  bordas  ",    "espaço_nas_bordas"),
    # Acentos preservados (NTFS suporta)
    ("Programação Orientada",      "Programação_Orientada"),
    # Hífens com espaço → hífen simples
    ("A - B - C",                  "A-B-C"),
    # Múltiplos underscores / hífens colapsados
    ("a___b",                      "a_b"),
    ("a---b",                      "a-b"),
    # String vazia após sanitização
    ("!!!",                        ""),
    # Ponto NÃO está em _SANITIZE_INVALID — é preservado
    ("Python 3.13 Tutorial",       "Python_3.13_Tutorial"),
])
def test_sanitize_filename_parametrize(title, expected):
    assert sanitize_filename(title) == expected


@pytest.mark.unit
def test_sanitize_filename_strip_leading_trailing():
    """Resultado nunca começa ou termina com '-', '_' ou '.'."""
    result = sanitize_filename("  - título -  ")
    assert not result.startswith(("-", "_", "."))
    assert not result.endswith(("-", "_", "."))


# ── format_duration ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("seconds, expected", [
    (0,     "00:00:00"),
    (59,    "00:00:59"),
    (60,    "00:01:00"),
    (3599,  "00:59:59"),
    (3600,  "01:00:00"),
    (7384,  "02:03:04"),
    (86400, "24:00:00"),
])
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


# ── extract_video_id ─────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("url, expected_len", [
    ("https://www.youtube.com/watch?v=ovabeVoWrA0", 6),
    ("https://youtu.be/ovabeVoWrA0",                6),
    ("https://youtu.be/dQw4w9WgXcQ",                6),
])
def test_extract_video_id_length(url, expected_len):
    result = extract_video_id(url)
    assert len(result) == expected_len
    assert result.isalnum()


@pytest.mark.unit
def test_extract_video_id_consistency():
    """Mesma URL sempre retorna mesmo slug."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url) == extract_video_id(url)


# ── format_metadata ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_format_metadata_contains_required_fields():
    meta = {
        "title": "Test Video",
        "uploader": "Test Channel",
        "upload_date": "20240115",
        "duration": 125,
        "tags": ["python", "test"],
    }
    result = format_metadata(meta, "https://youtu.be/abc123", detected_language="pt")
    assert "Test Video" in result
    assert "Test Channel" in result
    assert "2024-01-15" in result
    assert "00:02:05" in result
    assert "pt" in result
    assert "python, test" in result
    assert "-" * 64 in result


@pytest.mark.unit
def test_format_metadata_missing_fields_use_na():
    result = format_metadata({}, "https://youtu.be/abc123")
    assert "n/a" in result
