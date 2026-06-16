from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path: Path, monkeypatch):
    """Redireciona o módulo settings para usar tmp_path em vez de ~/.mill-tools."""
    cfg_dir = tmp_path / ".mill-tools"
    cfg_file = cfg_dir / "config.json"
    import src.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_file)


@pytest.mark.unit
def test_load_returns_defaults_when_no_file():
    from src.gui import settings

    data = settings.load()
    assert data["last_whisper_model"] == "small"
    assert data["theme_mode"] == "dark"
    assert data["last_beam_size"] == 1


@pytest.mark.unit
def test_load_includes_library_defaults():
    from src.gui import settings

    data = settings.load()
    assert data["last_library_filter"] == "all"
    assert data["last_library_category"] == "all"
    assert data["last_library_sort"] == "modified"
    assert data["last_library_view"] == "grid"


@pytest.mark.unit
def test_save_and_load_roundtrip():
    from src.gui import settings

    settings.save({"last_whisper_model": "large-v3", "theme_mode": "light"})
    data = settings.load()
    assert data["last_whisper_model"] == "large-v3"
    assert data["theme_mode"] == "light"
    assert "last_beam_size" in data


@pytest.mark.unit
def test_get_existing_key():
    from src.gui import settings

    settings.save({"last_language": "pt"})
    assert settings.get("last_language") == "pt"


@pytest.mark.unit
def test_get_missing_key_returns_default_param():
    from src.gui import settings

    assert settings.get("chave_inexistente", "fallback") == "fallback"


@pytest.mark.unit
def test_set_updates_single_key():
    from src.gui import settings

    settings.set("last_beam_size", 5)
    assert settings.get("last_beam_size") == 5


@pytest.mark.unit
def test_load_handles_corrupted_json(tmp_path: Path, monkeypatch):
    """Arquivo JSON corrompido deve retornar defaults sem lançar exceção."""
    cfg_dir = tmp_path / ".mill-tools-corrupt"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.json"
    cfg_file.write_text("{ invalid json }", encoding="utf-8")
    import src.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_file)
    data = settings_mod.load()
    assert data["last_whisper_model"] == "small"
