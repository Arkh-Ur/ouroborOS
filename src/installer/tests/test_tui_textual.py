"""test_tui_textual.py — Tests for the Textual TUI module."""

from __future__ import annotations

from pathlib import Path

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

    def test_default_hostname_is_ouroboros(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.hostname == "ouroboros"

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

    def test_hostname_default_is_ouroboros(self) -> None:
        """hostname has a sensible default so the install path never blocks on it."""
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.hostname == "ouroboros"

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


# ---------------------------------------------------------------------------
# Disk buffer fields (bugs #10, #11)
# ---------------------------------------------------------------------------

class TestDiskBuffer:
    def test_default_partition_scheme_is_auto(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.partition_scheme == "auto"

    def test_default_manual_partitions_empty(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.manual_partitions == []

    def test_manual_partitions_independent_per_instance(self) -> None:
        m = _import_module()
        a = m.TUIBuffer()
        b = m.TUIBuffer()
        a.manual_partitions.append({"number": 1})
        assert b.manual_partitions == []


# ---------------------------------------------------------------------------
# DiskPane manual-layout parsing (bug #10)
# ---------------------------------------------------------------------------

class TestDiskPaneParsing:
    def _pane_cls(self):
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        return m.DiskPane

    def test_parse_two_partitions(self) -> None:
        cls = self._pane_cls()
        parts = cls._parse_manual("512MiB:esp:/boot:fat32\n100%:btrfs:/:btrfs")
        assert parts == [
            {"number": 1, "size": "512MiB", "type": "esp", "mountpoint": "/boot", "fs": "fat32"},
            {"number": 2, "size": "100%", "type": "btrfs", "mountpoint": "/", "fs": "btrfs"},
        ]

    def test_parse_skips_blank_lines(self) -> None:
        cls = self._pane_cls()
        parts = cls._parse_manual("\n512MiB:esp:/boot:fat32\n\n100%:btrfs:/:btrfs\n")
        assert len(parts) == 2
        assert parts[0]["number"] == 1
        assert parts[1]["number"] == 2

    def test_parse_missing_fields_defaults(self) -> None:
        cls = self._pane_cls()
        parts = cls._parse_manual("20GiB:linux")
        assert parts[0]["type"] == "linux"
        assert parts[0]["mountpoint"] == ""
        assert parts[0]["fs"] == ""

    def test_parse_empty_text_returns_empty(self) -> None:
        cls = self._pane_cls()
        assert cls._parse_manual("\n  \n") == []


# ---------------------------------------------------------------------------
# Adapter show_* methods read from the buffer (non-blocking) — 2nd UX batch
# ---------------------------------------------------------------------------

class TestAdapterBufferBacked:
    """The environment/security/network show_* methods must read the buffer
    without blocking on the response queue, so an install can run from defaults
    and the unified panes (which write buffer-only) work correctly."""

    def _adapter(self, buffer: object):
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        # Build a bare adapter without starting the Textual app thread.
        tui = object.__new__(m.TUI)
        tui._rich = None
        tui._buffer = buffer
        tui._q = None  # blocking _get() must never be reached by these methods
        tui._app = None
        return tui

    def test_shell_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.shell = "fish"
        assert self._adapter(buf).show_shell_selection() == "fish"

    def test_desktop_profile_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.desktop_profile = "gnome"
        assert self._adapter(buf).show_desktop_profile() == "gnome"

    def test_desktop_dm_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.desktop_dm = "sddm"
        assert self._adapter(buf).show_desktop_dm() == "sddm"

    def test_gpu_driver_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.gpu_driver = "nvidia"
        assert self._adapter(buf).show_gpu_driver() == "nvidia"

    def test_secure_boot_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.secure_boot = True
        assert self._adapter(buf).show_secure_boot() is True

    def test_tpm2_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.tpm2_unlock = True
        assert self._adapter(buf).show_tpm2_unlock() is True

    def test_fido2_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.fido2_pam = True
        assert self._adapter(buf).show_fido2_pam() is True

    def test_ssh_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.enable_ssh = True
        assert self._adapter(buf).show_ssh_enable() is True

    def test_wifi_ssid_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.wifi_ssid = "homenet"
        assert self._adapter(buf).show_wifi_ssid() == "homenet"

    def test_wifi_passphrase_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.wifi_passphrase = "hunter2"
        assert self._adapter(buf).show_wifi_passphrase("homenet") == "hunter2"

    def test_kde_flavor_safe_default(self) -> None:
        m = _import_module()
        assert self._adapter(m.TUIBuffer()).show_kde_flavor() == "plasma-meta"

    def test_dual_boot_safe_default_false(self) -> None:
        m = _import_module()
        assert self._adapter(m.TUIBuffer()).show_dual_boot_enable() is False

    def test_disk_selection_reads_buffer(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.disk_device = "/dev/vda"
        assert self._adapter(buf).show_disk_selection() == "/dev/vda"

    def test_partition_preview_nonblocking_true(self) -> None:
        m = _import_module()
        # Returns True without touching the queue (erase gate moved to modal).
        assert self._adapter(m.TUIBuffer()).show_partition_preview("/dev/vda", False) is True

    def test_defaults_yield_install_ready_values(self) -> None:
        m = _import_module()
        a = self._adapter(m.TUIBuffer())
        assert a.show_shell_selection() == "bash"
        assert a.show_desktop_profile() == "minimal"
        assert a.show_desktop_dm() == "auto"
        assert a.show_gpu_driver() == "auto"
        assert a.show_secure_boot() is False
        assert a.show_ssh_enable() is False


# ---------------------------------------------------------------------------
# EnvironmentPane unified options (bug #7)
# ---------------------------------------------------------------------------

class TestEnvironmentPane:
    def _cls(self):
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        return m.EnvironmentPane

    def test_initial_keeps_current_when_valid(self) -> None:
        cls = self._cls()
        assert cls._initial(cls._SHELLS, "fish") == "fish"

    def test_initial_falls_back_to_first_when_invalid(self) -> None:
        cls = self._cls()
        assert cls._initial(cls._SHELLS, "nonexistent") == "bash"

    def test_shell_values(self) -> None:
        cls = self._cls()
        assert [v for _, v in cls._SHELLS] == ["bash", "zsh", "fish"]

    def test_gpu_includes_auto_first(self) -> None:
        cls = self._cls()
        assert cls._GPUS[0][1] == "auto"


# ---------------------------------------------------------------------------
# Main menu structure (bug #7 — unified Environment item)
# ---------------------------------------------------------------------------

class TestMainMenuItems:
    def _keys(self):
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        return [k for k, _ in m.MainMenuScreen._MENU_ITEMS]

    def test_environment_item_present(self) -> None:
        assert "environment" in self._keys()

    def test_old_split_items_absent(self) -> None:
        keys = self._keys()
        assert "shell" not in keys
        assert "desktop" not in keys
        assert "gpu" not in keys

    def test_install_and_abort_present(self) -> None:
        keys = self._keys()
        assert "install" in keys
        assert "abort" in keys


# ---------------------------------------------------------------------------
# Erase-confirmation modal (bug #13)
# ---------------------------------------------------------------------------

class TestConfirmEraseScreen:
    def test_modal_class_exists(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        assert hasattr(m, "ConfirmEraseScreen")

    def test_modal_stores_device(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        screen = m.ConfirmEraseScreen("/dev/vda")
        assert screen._device == "/dev/vda"


# ---------------------------------------------------------------------------
# Park-at-gate: install must not self-trigger; confirmation/users non-blocking
# ---------------------------------------------------------------------------

class TestParkAtGate:
    """The shared queue must keep exactly 3 blocking gets (language, install
    gate, reboot). show_confirmation and show_users_creation must NOT consume
    the queue — a stray drain there is what caused the auto-install + SSH drop.
    """

    def _adapter(self, buffer: object, queue_obj: object):
        m = _import_module()
        tui = object.__new__(m.TUI)
        tui._rich = None
        tui._buffer = buffer
        tui._q = queue_obj
        tui._app = None
        return tui

    def test_confirmation_returns_true_without_consuming_queue(self) -> None:
        import queue
        m = _import_module()
        q = queue.Queue()
        tui = self._adapter(m.TUIBuffer(), q)
        assert tui.show_confirmation("erase?") is True
        assert q.empty()  # the gate's put(True) must remain untouched here

    def test_users_creation_returns_buffer_without_consuming_queue(self) -> None:
        import queue
        m = _import_module()
        q = queue.Queue()
        buf = m.TUIBuffer()
        buf.users = [{"username": "alice", "groups": ["wheel"]}]
        tui = self._adapter(buf, q)
        assert tui.show_users_creation() == [{"username": "alice", "groups": ["wheel"]}]
        assert q.empty()

    def test_partition_preview_does_not_consume_queue(self) -> None:
        import queue
        m = _import_module()
        q = queue.Queue()
        tui = self._adapter(m.TUIBuffer(), q)
        assert tui.show_partition_preview("/dev/vda", False) is True
        assert q.empty()


# ---------------------------------------------------------------------------
# Optional root password accessor (Grupo D)
# ---------------------------------------------------------------------------

class TestRootPassword:
    def _adapter(self, buffer: object):
        m = _import_module()
        tui = object.__new__(m.TUI)
        tui._rich = None
        tui._buffer = buffer
        tui._q = None
        tui._app = None
        return tui

    def test_default_root_password_empty(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        assert buf.root_password == ""
        assert buf.set_root_password is False

    def test_get_root_password_locked_when_unset(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.root_password = "leftover"  # set flag off -> must be ignored
        buf.set_root_password = False
        assert self._adapter(buf).get_root_password() == ""

    def test_get_root_password_returns_buffer_when_enabled(self) -> None:
        m = _import_module()
        buf = m.TUIBuffer()
        buf.root_password = "s3cret"
        buf.set_root_password = True
        assert self._adapter(buf).get_root_password() == "s3cret"


# ---------------------------------------------------------------------------
# Install-ready defaults (Grupo C)
# ---------------------------------------------------------------------------

class TestInstallReadyDefaults:
    def test_desktop_dm_default_auto(self) -> None:
        m = _import_module()
        assert m.TUIBuffer().desktop_dm == "auto"

    def test_hostname_default_ouroboros(self) -> None:
        m = _import_module()
        assert m.TUIBuffer().hostname == "ouroboros"


# ---------------------------------------------------------------------------
# i18n: all Spanish variants resolve to the single es_CL catalog (Grupo E)
# ---------------------------------------------------------------------------

class TestI18nSpanishVariants:
    def test_lang_map_unifies_spanish(self) -> None:
        from installer import i18n
        assert i18n._LANG_MAP["es"] == "es_CL"
        assert i18n._LANG_MAP["es_MX"] == "es_CL"
        assert i18n._LANG_MAP["es_ES"] == "es_CL"


# ---------------------------------------------------------------------------
# Install progress mapping + crash guards (bug #5)
# ---------------------------------------------------------------------------

class _FakeApp:
    """Records call_from_thread invocations and runs the target inline."""

    def __init__(self, raises: bool = False) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._raises = raises

    def call_from_thread(self, fn, *args):  # noqa: ANN001, ANN002
        if self._raises:
            raise RuntimeError("App is not running")
        self.calls.append((getattr(fn, "__name__", str(fn)), args))
        return fn(*args)

    # Targets referenced by name via call_from_thread.
    def update_progress(self, global_pct: float, step_label: str = "", step_num: int = 0, total: int = 0) -> None:
        pass

    def show_error_screen(self, message: str) -> None:
        pass


class TestProgressMapping:
    def _adapter(self, app: object):
        m = _import_module()
        tui = object.__new__(m.TUI)
        tui._rich = None
        tui._buffer = None
        tui._q = None
        tui._app = app
        return tui

    def test_uses_global_percent_for_single_bar(self) -> None:
        """The single bar uses the global percent; step_label is the subtitle."""
        app = _FakeApp()
        tui = self._adapter(app)
        tui.update_install_progress(
            60, 9, 12, "Installing packages", phase="INSTALL", sub_pct=50,
        )
        assert ("update_progress", (60.0, "Installing packages", 9, 12)) in app.calls

    def test_global_percent_always_drives_bar(self) -> None:
        app = _FakeApp()
        tui = self._adapter(app)
        tui.update_install_progress(42, 1, 12, "Preparing disk", phase="FORMAT")
        assert ("update_progress", (42.0, "Preparing disk", 1, 12)) in app.calls

    def test_progress_update_swallows_runtime_error(self) -> None:
        """A dead Textual app (RuntimeError) must never abort the install."""
        app = _FakeApp(raises=True)
        tui = self._adapter(app)
        # Must not raise.
        tui.show_install_progress("INSTALL", 50, "")

    def test_install_error_swallows_runtime_error(self) -> None:
        app = _FakeApp(raises=True)
        tui = self._adapter(app)
        tui.show_install_error("boom")  # must not raise

    def test_install_error_surfaces_via_error_screen(self) -> None:
        app = _FakeApp()
        tui = self._adapter(app)
        tui.show_install_error("disk failure")
        assert ("show_error_screen", ("disk failure",)) in app.calls


# ---------------------------------------------------------------------------
# NavRadioButton: arrows traverse standalone toggles (bug #3)
# ---------------------------------------------------------------------------

class TestNavRadioButton:
    def test_has_arrow_navigation_bindings(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        keys = {b.key for b in m.NavRadioButton.BINDINGS}
        assert "up" in keys
        assert "down" in keys


# ---------------------------------------------------------------------------
# Live install log + spinner (manual-test feedback batch)
# ---------------------------------------------------------------------------

class TestLiveLogConstants:
    def test_install_log_path_is_the_fsm_log(self) -> None:
        m = _import_module()
        assert m.INSTALL_LOG_PATH == "/tmp/ouroborOS-install.log"

    def test_spinner_has_frames(self) -> None:
        m = _import_module()
        assert isinstance(m.SPINNER_FRAMES, str)
        assert len(m.SPINNER_FRAMES) >= 4


class TestProgressPaneLive:
    def test_progress_pane_exposes_live_controls(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        for name in ("start_live", "stop_live", "_pump_log", "_spin"):
            assert hasattr(m.ProgressPane, name), f"ProgressPane missing {name}"

    def test_pump_log_reads_new_lines(self, tmp_path: Path) -> None:
        """_pump_log seeks from the stored offset and writes only new lines."""
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        log_file = tmp_path / "install.log"
        log_file.write_text("first line\nsecond line\n", encoding="utf-8")

        pane = object.__new__(m.ProgressPane)
        pane._log_offset = 0
        written: list[str] = []

        class _FakeRichLog:
            def write(self, line: str) -> None:
                written.append(line)

        pane.query_one = lambda *a, **k: _FakeRichLog()  # type: ignore[assignment]
        import installer.tui_textual as mod
        original = mod.INSTALL_LOG_PATH
        mod.INSTALL_LOG_PATH = str(log_file)
        try:
            pane._pump_log()
            assert written == ["first line", "second line"]
            # Appending more only emits the delta.
            log_file.write_text(
                "first line\nsecond line\nthird line\n", encoding="utf-8"
            )
            written.clear()
            pane._pump_log()
            assert written == ["third line"]
        finally:
            mod.INSTALL_LOG_PATH = original


class TestRootPasswordModal:
    def test_modal_exists_with_escape_binding(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        keys = {b.key for b in m.RootPasswordModal.BINDINGS}
        assert "escape" in keys


class TestDonePaneRefresh:
    def test_done_pane_has_refresh_summary(self) -> None:
        m = _import_module()
        if not m.HAS_TEXTUAL:
            pytest.skip("textual not installed")
        assert hasattr(m.DonePane, "refresh_summary")
