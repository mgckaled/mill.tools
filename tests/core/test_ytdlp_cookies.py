"""Unit tests for src/core/ytdlp_cookies.py — no network, no real browser."""

import json

import pytest

from src.core import ytdlp_cookies as c

pytestmark = pytest.mark.unit


@pytest.fixture
def isolate(monkeypatch, tmp_path):
    """Point the module at a temp config, clear env, and disable Zen detection.

    Tests that exercise Zen re-patch ``resolve_zen_profile`` themselves, so the
    suite never depends on whether the dev machine has Zen installed.
    """
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(c, "_CONFIG_FILE", cfg)
    monkeypatch.delenv(c._ENV_BROWSER, raising=False)
    monkeypatch.delenv(c._ENV_PROFILE, raising=False)
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: None)
    return cfg


# ── _default_profile_from_ini ────────────────────────────────────────────────


def test_install_default_preferred_over_profile_default(tmp_path):
    app = tmp_path / "zen"
    app.mkdir()
    (app / "profiles.ini").write_text(
        "[Install123]\nDefault=Profiles/inst.prof\n\n"
        "[Profile0]\nName=legacy\nIsRelative=1\nPath=Profiles/leg\nDefault=1\n",
        encoding="utf-8",
    )
    assert c._default_profile_from_ini(app) == str(app / "Profiles/inst.prof")


def test_profile_default1_fallback(tmp_path):
    app = tmp_path / "zen"
    app.mkdir()
    (app / "profiles.ini").write_text(
        "[Profile0]\nPath=Profiles/a\nIsRelative=1\n\n"
        "[Profile1]\nPath=Profiles/b\nIsRelative=1\nDefault=1\n",
        encoding="utf-8",
    )
    assert c._default_profile_from_ini(app) == str(app / "Profiles/b")


def test_first_profile_when_no_default(tmp_path):
    app = tmp_path / "zen"
    app.mkdir()
    (app / "profiles.ini").write_text(
        "[Profile0]\nPath=Profiles/only\nIsRelative=1\n", encoding="utf-8"
    )
    assert c._default_profile_from_ini(app) == str(app / "Profiles/only")


def test_absolute_profile_path_kept(tmp_path):
    app = tmp_path / "zen"
    app.mkdir()
    abs_path = tmp_path / "elsewhere" / "prof"
    (app / "profiles.ini").write_text(
        f"[Profile0]\nIsRelative=0\nPath={abs_path}\nDefault=1\n", encoding="utf-8"
    )
    assert c._default_profile_from_ini(app) == str(abs_path)


def test_missing_ini_returns_none(tmp_path):
    assert c._default_profile_from_ini(tmp_path / "zen") is None


# ── resolve_zen_profile ──────────────────────────────────────────────────────


def test_resolve_zen_profile(tmp_path, monkeypatch):
    app = tmp_path / "zen"
    prof = app / "Profiles" / "p.default"
    prof.mkdir(parents=True)
    (app / "profiles.ini").write_text(
        "[Install1]\nDefault=Profiles/p.default\n", encoding="utf-8"
    )
    monkeypatch.setattr(c, "_zen_app_dir", lambda: app)
    assert c.resolve_zen_profile() == str(prof)


def test_resolve_zen_profile_none_when_app_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_zen_app_dir", lambda: tmp_path / "nope")
    assert c.resolve_zen_profile() is None


def test_resolve_zen_profile_none_when_profile_dir_missing(tmp_path, monkeypatch):
    app = tmp_path / "zen"
    app.mkdir()
    (app / "profiles.ini").write_text(
        "[Install1]\nDefault=Profiles/gone\n", encoding="utf-8"
    )
    monkeypatch.setattr(c, "_zen_app_dir", lambda: app)
    assert c.resolve_zen_profile() is None  # profile dir does not exist


# ── build_cookiesfrombrowser ─────────────────────────────────────────────────


@pytest.mark.parametrize("browser", ["", "none", "NONE"])
def test_build_none(browser):
    assert c.build_cookiesfrombrowser(browser) is None


def test_build_firefox():
    assert c.build_cookiesfrombrowser("firefox") == ("firefox", None, None, None)
    assert c.build_cookiesfrombrowser("firefox", "/p") == ("firefox", "/p", None, None)


@pytest.mark.parametrize(
    "browser", ["chrome", "edge", "brave", "chromium", "opera", "vivaldi"]
)
def test_build_chromium_family(browser):
    assert c.build_cookiesfrombrowser(browser) == (browser, None, None, None)


def test_build_unknown_returns_none():
    assert c.build_cookiesfrombrowser("netscape") is None


def test_build_zen_uses_resolved(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: "/zen/p")
    assert c.build_cookiesfrombrowser("zen") == ("firefox", "/zen/p", None, None)


def test_build_zen_explicit_profile(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: None)
    assert c.build_cookiesfrombrowser("zen", "/explicit") == (
        "firefox",
        "/explicit",
        None,
        None,
    )


def test_build_zen_none_when_undetected(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: None)
    assert c.build_cookiesfrombrowser("zen") is None


def test_build_auto_detected(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: "/zen/p")
    assert c.build_cookiesfrombrowser("auto") == ("firefox", "/zen/p", None, None)


def test_build_auto_none_when_undetected(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: None)
    assert c.build_cookiesfrombrowser("auto") is None


# ── cookie_ydl_opts (config + env) ───────────────────────────────────────────


def test_opts_disabled_via_config(isolate):
    isolate.write_text(json.dumps({"yt_cookies_browser": "none"}), encoding="utf-8")
    assert c.cookie_ydl_opts() == {}


def test_opts_from_config(isolate):
    isolate.write_text(json.dumps({"yt_cookies_browser": "chrome"}), encoding="utf-8")
    assert c.cookie_ydl_opts() == {"cookiesfrombrowser": ("chrome", None, None, None)}


def test_opts_env_overrides_config(isolate, monkeypatch):
    isolate.write_text(json.dumps({"yt_cookies_browser": "chrome"}), encoding="utf-8")
    monkeypatch.setenv(c._ENV_BROWSER, "firefox")
    assert c.cookie_ydl_opts() == {"cookiesfrombrowser": ("firefox", None, None, None)}


def test_opts_default_is_none(isolate, monkeypatch):
    # no config, no env → default "none" (opt-in) → no cookies, even if Zen exists
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: "/zen/p")
    assert c.cookie_ydl_opts() == {}


def test_opts_auto_detects_zen_when_chosen(isolate, monkeypatch):
    isolate.write_text(json.dumps({"yt_cookies_browser": "auto"}), encoding="utf-8")
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: "/zen/p")
    assert c.cookie_ydl_opts() == {
        "cookiesfrombrowser": ("firefox", "/zen/p", None, None)
    }


def test_opts_malformed_config_is_safe(isolate):
    isolate.write_text("{not valid json", encoding="utf-8")
    # malformed → {} read → default "none" → {}
    assert c.cookie_ydl_opts() == {}


def test_default_browser_is_opt_in():
    assert c.DEFAULT_BROWSER == "none"


# ── detected_summary ─────────────────────────────────────────────────────────


def test_summary_disabled():
    assert c.detected_summary("none") == "Cookies desativados"


def test_summary_zen_detected(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: "/zen/8ulb65hi.mgck")
    assert "8ulb65hi.mgck" in c.detected_summary("auto")


def test_summary_zen_not_detected(monkeypatch):
    monkeypatch.setattr(c, "resolve_zen_profile", lambda: None)
    assert "não detectado" in c.detected_summary("zen")


# ── merge into yt-dlp call sites ─────────────────────────────────────────────


class _FakeYDL:
    """Capture the opts passed to YoutubeDL; behave as a no-op context manager."""

    captured: dict = {}

    def __init__(self, opts):
        type(self).captured = opts

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def extract_info(self, url, download):
        return None


def test_fetch_metadata_forwards_cookies(monkeypatch, mocker):
    from src.core import metadata

    monkeypatch.setattr(
        "src.core.metadata.cookie_ydl_opts",
        lambda: {"cookiesfrombrowser": ("firefox", "/p", None, None)},
    )

    class _YDL(_FakeYDL):
        def extract_info(self, url, download):
            return {"title": "x"}

    mocker.patch("yt_dlp.YoutubeDL", _YDL)
    metadata.fetch_metadata("http://example/x")
    assert _YDL.captured["cookiesfrombrowser"] == ("firefox", "/p", None, None)
    assert _YDL.captured["noplaylist"] is True


def test_download_audio_forwards_cookies(tmp_path, monkeypatch, mocker):
    from src.core.audio import downloader

    monkeypatch.setattr(
        "src.core.audio.downloader.cookie_ydl_opts",
        lambda: {"cookiesfrombrowser": ("firefox", "/p", None, None)},
    )
    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    # extract_info returns None → no file produced → FileNotFoundError after capture.
    with pytest.raises(FileNotFoundError):
        downloader.download_audio(
            "http://example/x", tmp_path / "out", fmt="best", embed_meta=False
        )
    assert _FakeYDL.captured["cookiesfrombrowser"] == ("firefox", "/p", None, None)


def test_download_video_forwards_cookies(tmp_path, monkeypatch, mocker):
    from src.core.video import downloader

    monkeypatch.setattr(
        "src.core.video.downloader.cookie_ydl_opts",
        lambda: {"cookiesfrombrowser": ("firefox", "/p", None, None)},
    )
    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    with pytest.raises(FileNotFoundError):
        downloader.download_video(
            "http://example/x", tmp_path / "out", embed_meta=False
        )
    assert _FakeYDL.captured["cookiesfrombrowser"] == ("firefox", "/p", None, None)
