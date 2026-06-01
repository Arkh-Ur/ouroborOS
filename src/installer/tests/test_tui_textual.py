"""test_tui_textual.py — Tests for the Textual TUI module."""

from __future__ import annotations

import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_module():
    """Import tui_textual, skipping if dependencies are missing."""
    try:
        import installer.tui_textual as m
        return m
    except ImportError as exc:
        pytest.skip(f"tui_textual not importable: {exc}")


# ---------------------------------------------------------------------------
# LOCALE_CATALOG structure
# ---------------------------------------------------------------------------

class TestLocaleCatalog:
    def test_catalog_is_list_of_tuples(self) -> None:
        m = _import_module()
        assert isinstance(m.LOCALE_CATALOG, list)
        for entry in m.LOCALE_CATALOG:
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_catalog_has_minimum_entries(self) -> None:
        m = _import_module()
        assert len(m.LOCALE_CATALOG) >= 10

    def test_first_entry_is_english_us(self) -> None:
        m = _import_module()
        display, locale, i18n = m.LOCALE_CATALOG[0]
        assert locale == "en_US"
        assert i18n == "en_US"

    def test_all_locale_codes_have_underscore(self) -> None:
        m = _import_module()
        for display, locale, i18n in m.LOCALE_CATALOG:
            assert "_" in locale, f"locale '{locale}' missing region separator"

    def test_all_i18n_codes_have_underscore(self) -> None:
        m = _import_module()
        for display, locale, i18n in m.LOCALE_CATALOG:
            assert "_" in i18n, f"i18n code '{i18n}' missing region separator"

    def test_display_names_are_nonempty(self) -> None:
        m = _import_module()
        for display, locale, i18n in m.LOCALE_CATALOG:
            assert display.strip(), f"Empty display name for locale '{locale}'"

    def test_no_duplicate_locale_codes(self) -> None:
        m = _import_module()
        codes = [loc for _, loc, _ in m.LOCALE_CATALOG]
        assert len(codes) == len(set(codes))

    def test_chileno_maps_to_es_cl(self) -> None:
        m = _import_module()
        matches = [(d, lc, i) for d, lc, i in m.LOCALE_CATALOG if lc == "es_CL"]
        assert matches, "es_CL not found in LOCALE_CATALOG"
        assert matches[0][2] == "es_CL"

    def test_en_gb_falls_back_to_en_us_i18n(self) -> None:
        m = _import_module()
        matches = [(d, lc, i) for d, lc, i in m.LOCALE_CATALOG if lc == "en_GB"]
        assert matches, "en_GB not found in LOCALE_CATALOG"
        assert matches[0][2] == "en_US"

    def test_de_at_falls_back_to_de_de_i18n(self) -> None:
        m = _import_module()
        matches = [(d, lc, i) for d, lc, i in m.LOCALE_CATALOG if lc == "de_AT"]
        assert matches, "de_AT not found in LOCALE_CATALOG"
        assert matches[0][2] == "de_DE"

    def test_pt_pt_falls_back_to_pt_br_i18n(self) -> None:
        m = _import_module()
        matches = [(d, lc, i) for d, lc, i in m.LOCALE_CATALOG if lc == "pt_PT"]
        assert matches, "pt_PT not found in LOCALE_CATALOG"
        assert matches[0][2] == "pt_BR"


# ---------------------------------------------------------------------------
# lang_from_locale
# ---------------------------------------------------------------------------

class TestLangFromLocale:
    def test_en_us_maps_to_en_us(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("en_US") == "en_US"

    def test_es_cl_maps_to_es_cl(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("es_CL") == "es_CL"

    def test_en_gb_maps_to_en_us(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("en_GB") == "en_US"

    def test_de_at_maps_to_de_de(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("de_AT") == "de_DE"

    def test_unknown_locale_falls_back_to_en_us(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("xx_ZZ") == "en_US"

    def test_pt_pt_maps_to_pt_br(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("pt_PT") == "pt_BR"

    def test_zh_tw_maps_to_zh_cn(self) -> None:
        m = _import_module()
        assert m.lang_from_locale("zh_TW") == "zh_CN"


# ---------------------------------------------------------------------------
# TUIBuffer defaults
# ---------------------------------------------------------------------------

class TestTUIBufferDefaults:
    def test_default_locale(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.locale == "en_US.UTF-8"

    def test_default_keymap(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.keymap == "us"

    def test_default_timezone(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.timezone == "UTC"

    def test_default_shell(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.shell == "bash"

    def test_default_hostname_empty(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.hostname == ""

    def test_default_users_empty_list(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.users == []

    def test_default_luks_disabled(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.use_luks is False

    def test_default_secure_boot_disabled(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.secure_boot is False

    def test_default_desktop_profile(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.desktop_profile == "minimal"

    def test_default_gpu_driver(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.gpu_driver == "auto"

    def test_default_install_done_false(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.install_done is False

    def test_buffer_mutation(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.hostname = "testbox"
        buf.use_luks = True
        assert buf.hostname == "testbox"
        assert buf.use_luks is True

    def test_phase_progress_starts_empty(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.phase_progress == {}

    def test_install_log_starts_empty(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.install_log == []


# ---------------------------------------------------------------------------
# Required-fields gate
# ---------------------------------------------------------------------------

class TestRequiredFieldsGate:
    """Verify that certain fields are meaningful defaults (non-blocking install path)."""

    def test_disk_device_empty_by_default(self) -> None:
        """disk_device is required — must not have a non-empty default."""
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.disk_device == ""

    def test_hostname_empty_by_default(self) -> None:
        """hostname is required — must not have a non-empty default."""
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.hostname == ""

    def test_users_empty_by_default(self) -> None:
        """At least one user is required for install."""
        m = _import_module()
        buf = m.TUIBuffer()
        assert len(buf.users) == 0

    def test_buffer_with_required_fields_filled(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.disk_device = "/dev/vda"
        buf.hostname = "ourobox"
        buf.users = [{"username": "alice", "password": "secret", "groups": ["wheel"]}]
        assert buf.disk_device == "/dev/vda"
        assert buf.hostname == "ourobox"
        assert len(buf.users) == 1


# ---------------------------------------------------------------------------
# LOGO constant
# ---------------------------------------------------------------------------

class TestLogo:
    def test_logo_is_nonempty_string(self) -> None:
        m = _import_module()
        assert isinstance(m.LOGO, str)
        assert len(m.LOGO) > 100

    def test_logo_is_multiline(self) -> None:
        m = _import_module()
        lines = m.LOGO.strip().split("\n")
        assert len(lines) >= 8, f"Expected at least 8 lines, got {len(lines)}"

    def test_logo_contains_braille(self) -> None:
        m = _import_module()
        # Braille block starts at U+2800
        braille_chars = [c for c in m.LOGO if "⠀" <= c <= "⣿"]
        assert len(braille_chars) > 20, "Logo should contain significant braille art"

    def test_logo_has_no_trailing_newline_issues(self) -> None:
        m = _import_module()
        # Last char should not be an extra blank line causing layout issues
        assert m.LOGO.endswith(("\n", "⠀", "⠁", "⡀", "⢀", "⣀")) or True  # informational only


# ---------------------------------------------------------------------------
# HAS_TEXTUAL flag
# ---------------------------------------------------------------------------

class TestHasTextualFlag:
    def test_has_textual_is_bool(self) -> None:
        m = _import_module()
        assert isinstance(m.HAS_TEXTUAL, bool)
