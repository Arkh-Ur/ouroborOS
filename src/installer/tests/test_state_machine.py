"""test_state_machine.py — Tests for the installer FSM."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from installer.config import InstallerConfig
from installer.state_machine import (
    CHECKPOINT_DIR,
    FatalError,
    InstallerError,
    Installer,
    State,
    _checkpoint_path,
    _is_completed,
    _load_config_checkpoint,
    _save_checkpoint,
)


# ---------------------------------------------------------------------------
# Checkpoint system tests
# ---------------------------------------------------------------------------


class TestCheckpointSystem:
    def test_save_and_detect_checkpoint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(
            "installer.state_machine._checkpoint_path",
            lambda s: tmp_path / f"{s.name.lower()}.done",
        )
        cfg = InstallerConfig()
        _save_checkpoint(State.LOCALE, cfg)
        assert (tmp_path / "locale.done").exists()

    def test_is_completed_false_when_no_checkpoint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "installer.state_machine._checkpoint_path",
            lambda s: tmp_path / f"{s.name.lower()}.done",
        )
        assert _is_completed(State.PARTITION) is False

    def test_save_checkpoint_creates_config_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(
            "installer.state_machine._checkpoint_path",
            lambda s: tmp_path / f"{s.name.lower()}.done",
        )
        cfg = InstallerConfig()
        cfg.network.hostname = "test-host"
        _save_checkpoint(State.CONFIGURE, cfg)

        config_json = (tmp_path / "config.json").read_text(encoding="utf-8")
        data = json.loads(config_json)
        assert data["network"]["hostname"] == "test-host"


# ---------------------------------------------------------------------------
# State enum tests
# ---------------------------------------------------------------------------


class TestStateEnum:
    def test_all_expected_states_exist(self) -> None:
        expected = {
            "INIT", "PREFLIGHT", "LOCALE", "PARTITION",
            "FORMAT", "INSTALL", "CONFIGURE", "SNAPSHOT",
            "FINISH", "ERROR_RECOVERABLE", "FATAL",
        }
        actual = {s.name for s in State}
        assert expected == actual

    def test_state_values_are_unique(self) -> None:
        values = [s.value for s in State]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# InstallerConfig defaults
# ---------------------------------------------------------------------------


class TestInstallerConfigDefaults:
    def test_default_install_target(self) -> None:
        cfg = InstallerConfig()
        assert cfg.install_target == "/mnt"

    def test_default_disk_device_empty(self) -> None:
        cfg = InstallerConfig()
        assert cfg.disk.device == ""

    def test_default_locale_is_utf8(self) -> None:
        cfg = InstallerConfig()
        assert "UTF" in cfg.locale.locale

    def test_default_network_hostname(self) -> None:
        cfg = InstallerConfig()
        assert cfg.network.hostname == "ouroboros"

    def test_default_user_groups_includes_wheel(self) -> None:
        cfg = InstallerConfig()
        assert "wheel" in cfg.user.groups

    def test_unattended_defaults_to_false(self) -> None:
        cfg = InstallerConfig()
        assert cfg.unattended is False


# ---------------------------------------------------------------------------
# Installer FSM — preflight checks (unit, mocked)
# ---------------------------------------------------------------------------


class TestInstallerPreflight:
    def _make_installer(self) -> Installer:
        installer = Installer()
        installer.tui = None
        return installer

    def test_check_root_passes_as_root(self) -> None:
        installer = self._make_installer()
        with patch("os.geteuid", return_value=0):
            installer._check_root()  # Should not raise

    def test_check_root_fails_as_non_root(self) -> None:
        installer = self._make_installer()
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(InstallerError, match="root"):
                installer._check_root()

    def test_check_uefi_passes_when_efi_exists(self, tmp_path: Path) -> None:
        installer = self._make_installer()
        efi_path = tmp_path / "efi"
        efi_path.mkdir()
        with patch("installer.state_machine.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            # Direct test: patch /sys/firmware/efi
            with patch("pathlib.Path.exists", return_value=True):
                installer._check_uefi()

    def test_check_uefi_fails_when_no_efi(self) -> None:
        installer = self._make_installer()
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(InstallerError, match="UEFI"):
                installer._check_uefi()

    def test_check_tools_passes_when_all_present(self) -> None:
        installer = self._make_installer()
        with patch.object(Installer, "_which", return_value=True):
            installer._check_tools()

    def test_check_tools_fails_when_missing(self) -> None:
        installer = self._make_installer()
        with patch.object(Installer, "_which", return_value=False):
            with pytest.raises(InstallerError, match="Missing"):
                installer._check_tools()

    def test_check_ram_passes_with_sufficient_memory(self) -> None:
        installer = self._make_installer()
        meminfo = "MemTotal:       4096000 kB\nMemFree: 2048000 kB\n"
        with patch("pathlib.Path.read_text", return_value=meminfo):
            installer._check_ram()

    def test_check_ram_fails_with_insufficient_memory(self) -> None:
        installer = self._make_installer()
        meminfo = "MemTotal:       512000 kB\nMemFree: 256000 kB\n"
        with patch("pathlib.Path.read_text", return_value=meminfo):
            with pytest.raises(InstallerError, match="RAM"):
                installer._check_ram()


# ---------------------------------------------------------------------------
# Installer FSM — full run (mocked)
# ---------------------------------------------------------------------------


class TestInstallerRun:
    def _make_fully_mocked_installer(self) -> Installer:
        """Return an Installer with all state handlers and the handler map mocked."""
        installer = Installer()
        # Replace both the bound methods AND the handler_map entries
        state_method_pairs = [
            (State.INIT, "_handle_init"),
            (State.PREFLIGHT, "_handle_preflight"),
            (State.LOCALE, "_handle_locale"),
            (State.PARTITION, "_handle_partition"),
            (State.FORMAT, "_handle_format"),
            (State.INSTALL, "_handle_install"),
            (State.CONFIGURE, "_handle_configure"),
            (State.SNAPSHOT, "_handle_snapshot"),
            (State.FINISH, "_handle_finish"),
        ]
        for state, name in state_method_pairs:
            mock = MagicMock()
            setattr(installer, name, mock)
            installer._handler_map[state] = mock
        return installer

    def test_successful_run_returns_zero(self) -> None:
        installer = self._make_fully_mocked_installer()
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 0

    def test_fatal_error_returns_one(self) -> None:
        installer = self._make_fully_mocked_installer()
        installer.tui = None
        mock_fatal = MagicMock(side_effect=FatalError("boom"))
        installer._handler_map[State.INIT] = mock_fatal
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1

    def test_unattended_mode_aborts_on_first_error(self) -> None:
        """In unattended mode (no TUI), the installer aborts on the first error."""
        installer = self._make_fully_mocked_installer()
        installer.tui = None
        call_count = 0

        def flaky_handler() -> None:
            nonlocal call_count
            call_count += 1
            raise InstallerError("transient error")

        installer._handler_map[State.INIT] = flaky_handler

        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()

        # Unattended mode does not retry — abort on first error
        assert call_count == 1
        assert result == 1

    def test_tui_mode_retries_recoverable_error(self) -> None:
        """In interactive mode, the TUI prompts for retry up to max_retries."""
        installer = self._make_fully_mocked_installer()
        mock_tui = MagicMock()
        mock_tui.show_error.return_value = True  # User always chooses Retry
        installer.tui = mock_tui
        call_count = 0

        def flaky_handler() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise InstallerError("transient error")

        installer._handler_map[State.INIT] = flaky_handler

        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()

        assert call_count == 3
        assert result == 0

    def test_too_many_retries_causes_fatal(self) -> None:
        installer = self._make_fully_mocked_installer()
        installer.tui = None
        installer._handler_map[State.INIT] = MagicMock(
            side_effect=InstallerError("persistent error")
        )
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1

    def test_keyboard_interrupt_returns_one(self) -> None:
        installer = self._make_fully_mocked_installer()
        installer.tui = None
        installer._handler_map[State.INIT] = MagicMock(side_effect=KeyboardInterrupt)
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1

    def test_resume_skips_completed_states(self) -> None:
        installer = Installer(resume=True)
        installer.tui = None

        called_states: list[str] = []

        def make_tracker(state_name: str):
            def handler():
                called_states.append(state_name)
            return handler

        # Replace both bound methods and handler_map entries
        state_method_pairs = [
            (State.INIT, "_handle_init"),
            (State.PREFLIGHT, "_handle_preflight"),
            (State.LOCALE, "_handle_locale"),
            (State.PARTITION, "_handle_partition"),
            (State.FORMAT, "_handle_format"),
            (State.INSTALL, "_handle_install"),
            (State.CONFIGURE, "_handle_configure"),
            (State.SNAPSHOT, "_handle_snapshot"),
            (State.FINISH, "_handle_finish"),
        ]
        for state, name in state_method_pairs:
            tracker = make_tracker(name)
            setattr(installer, name, tracker)
            installer._handler_map[state] = tracker

        with patch("installer.state_machine._is_completed") as mock_done, \
             patch("installer.state_machine._save_checkpoint"), \
             patch("installer.state_machine._load_config_checkpoint", return_value=None):
            mock_done.side_effect = lambda s: s in (State.INIT, State.PREFLIGHT)
            installer.run()

        assert "_handle_init" not in called_states
        assert "_handle_preflight" not in called_states
        assert "_handle_locale" in called_states
