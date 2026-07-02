"""Unit tests for src/gui/views/form_env.py — .env read/write for cloud API keys.

isolate_env (autouse) redirects _ENV_FILE to tmp_path for every test in this
file — these tests must never touch the project's real .env, which may hold
real secrets. Only placeholder values are used below.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_env(tmp_path: Path, monkeypatch):
    import src.gui.views.form_env as form_env_mod

    monkeypatch.setattr(form_env_mod, "_ENV_FILE", tmp_path / ".env")


@pytest.mark.unit
def test_read_api_key_missing_file_returns_empty():
    from src.gui.views.form_env import read_api_key

    assert read_api_key() == ""


@pytest.mark.unit
def test_write_then_read_api_key_roundtrip():
    from src.gui.views.form_env import read_api_key, write_api_key

    write_api_key("fake-google-key-123")
    assert read_api_key() == "fake-google-key-123"


@pytest.mark.unit
def test_write_then_read_glm_api_key_roundtrip():
    from src.gui.views.form_env import read_glm_api_key, write_glm_api_key

    write_glm_api_key("fake-zhipu-key-456")
    assert read_glm_api_key() == "fake-zhipu-key-456"


@pytest.mark.unit
def test_write_api_key_empty_value_is_noop(tmp_path: Path):
    """Blurring an empty field must not erase an existing key."""
    from src.gui.views.form_env import read_api_key, write_api_key

    write_api_key("fake-google-key-123")
    write_api_key("")
    assert read_api_key() == "fake-google-key-123"


@pytest.mark.unit
def test_write_api_key_updates_existing_line_in_place():
    from src.gui.views.form_env import read_api_key, write_api_key

    write_api_key("old-fake-key")
    write_api_key("new-fake-key")
    assert read_api_key() == "new-fake-key"


@pytest.mark.unit
def test_write_does_not_disturb_other_keys(tmp_path: Path):
    """GOOGLE_API_KEY and ZHIPU_API_KEY must coexist independently in .env."""
    from src.gui.views.form_env import (
        read_api_key,
        read_glm_api_key,
        write_api_key,
        write_glm_api_key,
    )

    write_api_key("fake-google-key")
    write_glm_api_key("fake-zhipu-key")
    write_api_key("fake-google-key-updated")

    assert read_api_key() == "fake-google-key-updated"
    assert read_glm_api_key() == "fake-zhipu-key"


@pytest.mark.unit
def test_write_preserves_unrelated_env_lines(tmp_path: Path):
    """Existing non-key lines in .env (comments, other vars) survive a write."""
    from src.gui.views.form_env import _ENV_FILE, read_api_key, write_api_key

    _ENV_FILE.write_text("SOME_OTHER_VAR=keep-me\n", encoding="utf-8")
    write_api_key("fake-google-key")

    assert read_api_key() == "fake-google-key"
    assert "SOME_OTHER_VAR=keep-me" in _ENV_FILE.read_text(encoding="utf-8")
