"""YouTube cookies for yt-dlp — isolated, reusable across every download call site.

YouTube intermittently gates downloads with an anti-bot check ("Sign in to confirm
you're not a bot"). The reliable workaround is to send cookies from a logged-in
browser via yt-dlp's ``cookiesfrombrowser`` option.

This module is the single place that knows how to resolve those cookies. Every yt-dlp
call site (audio/video downloaders, metadata fetch) merges ``cookie_ydl_opts()`` into
its options, so Áudio, Vídeo, Transcrição, Receitas and the CLI are all covered without
threading a parameter through each call.

Zen Browser is not a browser yt-dlp knows by name, but it stores cookies in the standard
Firefox ``cookies.sqlite`` format. We point yt-dlp at Zen by using the ``firefox`` engine
with the absolute path of the Zen profile directory (yt-dlp accepts an absolute path as
the profile and reads ``cookies.sqlite`` from it).

The module is pure (no Flet, no GUI imports) and reads its configuration from env vars or
``~/.mill-tools/config.json`` directly, so it stays usable by both CLI and GUI.
"""

from __future__ import annotations

import configparser
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Config file shared with the GUI. Kept as a local constant (mirrors src/gui/settings.py)
# to avoid a core -> gui import. Env vars take precedence for CLI / power users.
_CONFIG_FILE = Path.home() / ".mill-tools" / "config.json"
_ENV_BROWSER = "MILL_YT_COOKIES_BROWSER"
_ENV_PROFILE = "MILL_YT_COOKIES_PROFILE"

# yt-dlp browser keys (see SUPPORTED_BROWSERS in yt_dlp/cookies.py). "zen" is ours: it
# maps to the firefox engine plus the absolute Zen profile path.
_CHROMIUM = ("chrome", "edge", "brave", "chromium", "opera", "vivaldi")

# Friendly options for the GUI dropdown (order matters). "safari" only on macOS.
BROWSERS: list[str] = ["auto", "none", "zen", "firefox", *_CHROMIUM]
if sys.platform == "darwin":
    BROWSERS.append("safari")

DEFAULT_BROWSER = "auto"


def _read_config() -> dict:
    """Read the persisted user config (mirrors gui.settings); {} on any failure."""
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _configured() -> tuple[str, str]:
    """Return (browser, profile) from env vars, then config file, then defaults."""
    cfg = _read_config()
    browser = (
        os.environ.get(_ENV_BROWSER) or cfg.get("yt_cookies_browser") or DEFAULT_BROWSER
    )
    profile = os.environ.get(_ENV_PROFILE) or cfg.get("yt_cookies_profile") or ""
    return browser.strip().lower(), profile.strip()


def _zen_app_dir() -> Path | None:
    """Return the Zen Browser data dir for the current platform, or None."""
    if sys.platform in ("win32", "cygwin"):
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "zen" if appdata else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "zen"
    return Path.home() / ".zen"


def _default_profile_from_ini(app_dir: Path) -> str | None:
    """Resolve the default profile path from a Firefox/Zen ``profiles.ini``.

    Prefers the install section's ``Default=`` (the profile the browser actually
    launches), then a ``[Profile*]`` with ``Default=1``, then the first profile.
    Returns an absolute path, or None if it cannot be resolved.
    """
    ini = app_dir / "profiles.ini"
    if not ini.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(ini, encoding="utf-8")
    except (configparser.Error, OSError):
        return None

    def _resolve(path_str: str) -> str:
        p = Path(path_str)
        return str(p if p.is_absolute() else app_dir / path_str)

    # 1) [Install*].Default — what the browser launches with (modern Firefox/Zen).
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            return _resolve(parser.get(section, "Default"))

    # 2) [Profile*] with Default=1, else the first [Profile*].
    first_profile: str | None = None
    for section in parser.sections():
        if not section.startswith("Profile") or not parser.has_option(section, "Path"):
            continue
        resolved = _resolve(parser.get(section, "Path"))
        if first_profile is None:
            first_profile = resolved
        if parser.get(section, "Default", fallback="0") == "1":
            return resolved
    return first_profile


def resolve_zen_profile() -> str | None:
    """Absolute path of the default Zen profile dir, or None if not found/usable."""
    app_dir = _zen_app_dir()
    if not app_dir or not app_dir.is_dir():
        return None
    profile = _default_profile_from_ini(app_dir)
    if profile and Path(profile).is_dir():
        return profile
    return None


def build_cookiesfrombrowser(browser: str, profile: str | None = None) -> tuple | None:
    """Map a friendly browser name to a yt-dlp ``cookiesfrombrowser`` tuple.

    Returns ``(browser_name, profile, keyring, container)`` or None when cookies
    should not be used. ``profile`` may be an absolute path — yt-dlp reads it directly.
    """
    browser = (browser or "").strip().lower()
    profile = (profile or "").strip() or None

    if browser in ("", "none"):
        return None

    if browser == "auto":
        zen = resolve_zen_profile()
        return ("firefox", zen, None, None) if zen else None

    if browser == "zen":
        zen_profile = profile or resolve_zen_profile()
        if not zen_profile:
            logger.warning("[!] Zen cookies requested but no Zen profile was found")
            return None
        return ("firefox", zen_profile, None, None)

    if browser == "firefox":
        return ("firefox", profile, None, None)

    if browser in _CHROMIUM or browser == "safari":
        return (browser, profile, None, None)

    logger.warning("[!] Unknown cookies browser %r — ignoring", browser)
    return None


def cookie_ydl_opts() -> dict:
    """yt-dlp options to merge into any download/extract call.

    Returns ``{"cookiesfrombrowser": (...)}`` when cookies are configured/detected, or
    ``{}`` otherwise. Never raises — cookie resolution must not break a download.
    """
    try:
        browser, profile = _configured()
        spec = build_cookiesfrombrowser(browser, profile)
        if spec is None:
            return {}
        logger.info(
            "[i] Using cookies from browser=%s profile=%s",
            spec[0],
            spec[1] or "(default)",
        )
        return {"cookiesfrombrowser": spec}
    except Exception as exc:  # never let cookie resolution break a download
        logger.warning(
            "[!] Cookie resolution failed (%s) — continuing without cookies", exc
        )
        return {}


def detected_summary(browser: str | None = None, profile: str | None = None) -> str:
    """Human-readable status of the cookie source, for the settings dialog.

    With no args, reflects the persisted/effective config. Pass a browser/profile to
    preview a selection before saving.
    """
    if browser is None:
        browser, profile = _configured()
    browser = (browser or "").strip().lower()

    if browser in ("", "none"):
        return "Cookies desativados"

    spec = build_cookiesfrombrowser(browser, profile)
    if spec is None:
        if browser in ("auto", "zen"):
            return "Zen não detectado — nenhum cookie será usado"
        return f"{browser}: nenhum perfil detectado"

    _engine, prof = spec[0], spec[1]
    if browser in ("auto", "zen"):
        name = Path(prof).name if prof else "?"
        return f"Zen detectado — perfil '{name}'"
    if prof:
        return f"{browser} — perfil '{Path(prof).name}'"
    return f"{browser} — perfil padrão"
