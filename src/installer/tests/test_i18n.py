"""test_i18n.py — Tests for the i18n module."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

import installer.i18n as i18n_mod
from installer.i18n import _, init_i18n


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_i18n() -> None:
    """Reset i18n module to NullTranslations (English passthrough)."""
    import gettext
    i18n_mod._translation = gettext.NullTranslations()


# ---------------------------------------------------------------------------
# NullTranslations passthrough (before init_i18n is called)
# ---------------------------------------------------------------------------


class TestNullTranslations:
    def setup_method(self) -> None:
        _reset_i18n()

    def test_returns_string_unchanged(self) -> None:
        assert _("Hello world") == "Hello world"

    def test_empty_string_passthrough(self) -> None:
        assert _("") == ""

    def test_unicode_passthrough(self) -> None:
        assert _("Bienvenido") == "Bienvenido"


# ---------------------------------------------------------------------------
# init_i18n — fallback to English when no .mo file found
# ---------------------------------------------------------------------------


class TestInitI18nFallback:
    def setup_method(self) -> None:
        _reset_i18n()

    def test_unknown_language_falls_back_silently(self) -> None:
        init_i18n("xx_UNKNOWN")
        assert _("Welcome to the ouroborOS installer.") == "Welcome to the ouroborOS installer."

    def test_short_alias_en_falls_back_gracefully(self) -> None:
        # "en" maps to "en_US" — may or may not have .mo; either way, no exception.
        init_i18n("en")
        # Should at minimum return a string (passthrough if no .mo file).
        result = _("Welcome to the ouroborOS installer.")
        assert isinstance(result, str)

    def test_invalid_language_does_not_raise(self) -> None:
        init_i18n("")  # empty string — must not raise
        assert _("test") == "test"


# ---------------------------------------------------------------------------
# SUPPORTED_LANGUAGES constant
# ---------------------------------------------------------------------------


class TestSupportedLanguages:
    def test_contains_english(self) -> None:
        codes = [code for code, _ in i18n_mod.SUPPORTED_LANGUAGES]
        assert "en_US" in codes

    def test_contains_spanish(self) -> None:
        codes = [code for code, _ in i18n_mod.SUPPORTED_LANGUAGES]
        assert "es_AR" in codes

    def test_contains_german(self) -> None:
        codes = [code for code, _ in i18n_mod.SUPPORTED_LANGUAGES]
        assert "de_DE" in codes

    def test_each_entry_is_two_tuple(self) -> None:
        for entry in i18n_mod.SUPPORTED_LANGUAGES:
            assert len(entry) == 2

    def test_labels_are_non_empty(self) -> None:
        for _, label in i18n_mod.SUPPORTED_LANGUAGES:
            assert label


# ---------------------------------------------------------------------------
# init_i18n with a real .mo file (compiled at test time if possible)
# ---------------------------------------------------------------------------


class TestInitI18nWithMoFile:
    """Compile en_US.po on-the-fly and verify NullTranslations is used."""

    def setup_method(self) -> None:
        _reset_i18n()

    def test_es_ar_translation_with_compiled_mo(self, tmp_path: Path) -> None:
        """Build a minimal .mo from a known msgid/msgstr pair and verify translation."""
        import subprocess
        import shutil

        if not shutil.which("msgfmt"):
            pytest.skip("msgfmt not available — gettext not installed")

        # Create a minimal .po file
        po_content = (
            'msgid ""\n'
            'msgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n'
            '"Language: es_AR\\n"\n'
            "\n"
            'msgid "Welcome to the ouroborOS installer."\n'
            'msgstr "Bienvenido al instalador de ouroborOS."\n'
        )
        po_path = tmp_path / "es_AR" / "LC_MESSAGES" / "installer.po"
        po_path.parent.mkdir(parents=True)
        po_path.write_text(po_content, encoding="utf-8")

        mo_path = po_path.with_suffix(".mo")
        result = subprocess.run(
            ["msgfmt", "-o", str(mo_path), str(po_path)],
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip("msgfmt compilation failed")

        # Point the i18n module at our temp locale dir and init
        with patch.object(i18n_mod, "_LOCALE_DIR", tmp_path):
            init_i18n("es_AR")
            translated = _("Welcome to the ouroborOS installer.")

        assert translated == "Bienvenido al instalador de ouroborOS."
        _reset_i18n()
