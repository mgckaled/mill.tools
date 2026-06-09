import pytest
from src.core.metadata import format_duration, format_metadata


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
