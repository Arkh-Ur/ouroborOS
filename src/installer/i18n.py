"""i18n.py — Internationalization support for the ouroborOS installer.

Uses Python's built-in gettext module with compiled .mo files located in
``src/installer/locale/<lang>/LC_MESSAGES/installer.mo``.

The ``_()`` function is a no-op (NullTranslations) until ``init_i18n()``
is called.  This means all strings remain in English before the user picks
a language — which is intentional.

Usage::

    from installer.i18n import _, init_i18n

    init_i18n("es_CL")          # call once, after language selection
    print(_("Select disk:"))    # returns translated string
"""

from __future__ import annotations

import gettext
from pathlib import Path

_LOCALE_DIR = Path(__file__).parent / "locale"
_DOMAIN = "installer"

# Start with passthrough — before init_i18n() is called all strings
# are returned unchanged (English source strings).
_translation: gettext.NullTranslations = gettext.NullTranslations()

# Short-form language aliases → canonical locale codes.
_LANG_MAP: dict[str, str] = {
    "en":    "en_US",
    "es":    "es_CL",
    "de":    "de_DE",
}

# Languages supported by this build (matching locale/ subdirectories).
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("en_US", "English (US)"),
    ("es_CL", "Español (Chile)"),
    ("de_DE", "Deutsch (Deutschland)"),
]


def init_i18n(lang: str) -> None:
    """Initialise gettext for *lang*.

    Must be called once, before any user-facing strings are displayed.
    Falls back silently to English (NullTranslations) if the requested
    language has no compiled .mo file.

    Args:
        lang: Language code — canonical (``"en_US"``, ``"es_CL"``,
              ``"de_DE"``) or short alias (``"en"``, ``"es"``, ``"de"``).
    """
    global _translation

    resolved = _LANG_MAP.get(lang, lang)

    try:
        _translation = gettext.translation(
            _DOMAIN,
            localedir=str(_LOCALE_DIR),
            languages=[resolved],
        )
    except FileNotFoundError:
        # No .mo file for this language — silently use English passthrough.
        _translation = gettext.NullTranslations()


def _(message: str) -> str:  # noqa: N802
    """Return the translated form of *message* in the active language.

    Wraps ``gettext.NullTranslations.gettext()`` before ``init_i18n()``
    is called, and the real translation after.
    """
    return _translation.gettext(message)


def lang_from_locale(locale_code: str) -> str:
    """Map a locale_code to its i18n initialisation code.

    Uses the LOCALE_CATALOG defined in ``tui_textual`` when available;
    falls back to the built-in ``_LANG_MAP`` alias table otherwise.

    Args:
        locale_code: A locale code such as ``"en_US"`` or ``"es_CL"``.

    Returns:
        The corresponding i18n code accepted by ``init_i18n()``, e.g.
        ``"en_US"`` or ``"es_CL"``.  Falls back to ``"en_US"`` if the
        code is not recognised.
    """
    try:
        from installer.tui_textual import lang_from_locale as _ttx_lang  # type: ignore[import]
        return _ttx_lang(locale_code)
    except ImportError:
        pass
    # Fallback: strip region and use _LANG_MAP
    short = locale_code.split("_")[0].lower()
    return _LANG_MAP.get(short, locale_code)
