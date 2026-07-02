"""Construct-smoke for the global Settings dialog (AppBar gear icon).

isolate_env (autouse) redirects form_env._ENV_FILE to tmp_path — these tests
must never touch the project's real .env, which may hold real secrets. Only
placeholder values are used below. isolate_config does the same for
gui.settings (~/.mill-tools/config.json), following the same pattern already
used in tests/gui/test_settings.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
import pytest


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    import src.gui.views.form_env as form_env_mod

    monkeypatch.setattr(form_env_mod, "_ENV_FILE", tmp_path / ".env")


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    import src.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", tmp_path / ".mill-tools")
    monkeypatch.setattr(
        settings_mod, "_CONFIG_FILE", tmp_path / ".mill-tools" / "config.json"
    )


def _open(page: MagicMock) -> ft.AlertDialog:
    from src.gui.settings_dialog import open_settings_dialog

    open_settings_dialog(page)
    return page.show_dialog.call_args.args[0]


def _section_titles(dlg: ft.AlertDialog) -> list[str]:
    column = dlg.content.content
    return [
        c.controls[0].value
        for c in column.controls
        if isinstance(c, ft.Column)
        and c.controls
        and isinstance(c.controls[0], ft.Text)
    ]


def _credentials_section(dlg: ft.AlertDialog) -> ft.Column:
    column = dlg.content.content
    return next(
        c
        for c in column.controls
        if isinstance(c, ft.Column)
        and c.controls
        and getattr(c.controls[0], "value", None) == "Credenciais"
    )


@pytest.mark.unit
def test_settings_dialog_builds_without_raising():
    dlg = _open(MagicMock())
    assert dlg is not None


@pytest.mark.unit
def test_credentials_section_is_the_last_section():
    titles = _section_titles(_open(MagicMock()))
    assert titles[-1] == "Credenciais"
    assert titles.index("Credenciais") > titles.index("Cookies do YouTube")


@pytest.mark.unit
def test_api_key_fields_prefilled_from_env():
    from src.gui.views.form_env import write_api_key, write_glm_api_key

    write_api_key("fake-google-key")
    write_glm_api_key("fake-zhipu-key")

    creds = _credentials_section(_open(MagicMock()))
    api_field, glm_field = creds.controls[1], creds.controls[2]
    assert api_field.value == "fake-google-key"
    assert glm_field.value == "fake-zhipu-key"


@pytest.mark.unit
def test_api_key_field_on_blur_persists_to_env():
    from src.gui.views.form_env import read_api_key

    creds = _credentials_section(_open(MagicMock()))
    api_field = creds.controls[1]
    api_field.value = "typed-fake-key"
    api_field.on_blur(MagicMock())

    assert read_api_key() == "typed-fake-key"


@pytest.mark.unit
def test_glm_api_key_field_on_blur_persists_to_env():
    from src.gui.views.form_env import read_glm_api_key

    creds = _credentials_section(_open(MagicMock()))
    glm_field = creds.controls[2]
    glm_field.value = "typed-fake-glm-key"
    glm_field.on_blur(MagicMock())

    assert read_glm_api_key() == "typed-fake-glm-key"


@pytest.mark.unit
def test_api_key_fields_mask_input():
    creds = _credentials_section(_open(MagicMock()))
    api_field, glm_field = creds.controls[1], creds.controls[2]
    assert api_field.password is True
    assert glm_field.password is True
