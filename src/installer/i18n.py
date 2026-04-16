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
