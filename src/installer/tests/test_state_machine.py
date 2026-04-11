"""test_state_machine.py — Tests for the installer FSM."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from installer.config import InstallerConfig
from installer.state_machine import (
    FatalError,
    Installer,
    InstallerError,
    State,
    _is_completed,
    _load_config_checkpoint,
    _save_checkpoint,
)

# ---------------------------------------------------------------------------
# Checkpoint system tests
# ---------------------------------------------------------------------------


class TestCheckpointSystem:
    def test_save_and_detect_checkpoint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(
            "installer.state_machine._checkpoint_path",
            lambda s: tmp_path / f"{s.name.lower()}.done",
        )
        cfg = InstallerConfig()
        _save_checkpoint(State.LOCALE, cfg)
        assert (tmp_path / "locale.done").exists()

    def test_is_completed_false_when_no_checkpoint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "installer.state_machine._checkpoint_path",
            lambda s: tmp_path / f"{s.name.lower()}.done",
        )
        assert _is_completed(State.PARTITION) is False

    def test_save_checkpoint_creates_config_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
            "INIT", "PREFLIGHT", "LOCALE", "USER", "DESKTOP",
            "SECURE_BOOT",
            "PARTITION", "FORMAT", "INSTALL", "CONFIGURE", "SNAPSHOT",
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
            (State.USER, "_handle_user"),
            (State.DESKTOP, "_handle_desktop"),
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
        mock_tui.show_dm_selection.return_value = "auto"
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
            (State.USER, "_handle_user"),
            (State.DESKTOP, "_handle_desktop"),
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
             patch(
                 "installer.state_machine._load_config_checkpoint", return_value=None
             ):
            mock_done.side_effect = lambda s: s in (State.INIT, State.PREFLIGHT)
            installer.run()

        assert "_handle_init" not in called_states
        assert "_handle_preflight" not in called_states
        assert "_handle_locale" in called_states


# ---------------------------------------------------------------------------
# _load_config_checkpoint
# ---------------------------------------------------------------------------


class TestLoadConfigCheckpoint:
    def test_returns_none_when_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        assert _load_config_checkpoint() is None

    def test_restores_config_from_valid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        cfg = InstallerConfig()
        cfg.network.hostname = "restored-host"
        import json
        from dataclasses import asdict
        (tmp_path / "config.json").write_text(json.dumps(asdict(cfg)), encoding="utf-8")

        result = _load_config_checkpoint()
        assert result is not None
        assert result.network.hostname == "restored-host"

    def test_returns_none_on_invalid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("installer.state_machine.CHECKPOINT_DIR", tmp_path)
        (tmp_path / "config.json").write_text("not valid json", encoding="utf-8")
        assert _load_config_checkpoint() is None


# ---------------------------------------------------------------------------
# Installer._detect_microcode_package
# ---------------------------------------------------------------------------


class TestDetectMicrocodePackage:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst.tui = None
        return inst

    def test_detects_intel(self) -> None:
        installer = self._make_installer()
        with patch("pathlib.Path.read_text", return_value="flags: GenuineIntel fpu"):
            assert installer._detect_microcode_package() == "intel-ucode"

    def test_detects_amd(self) -> None:
        installer = self._make_installer()
        with patch("pathlib.Path.read_text", return_value="flags: AuthenticAMD fpu"):
            assert installer._detect_microcode_package() == "amd-ucode"

    def test_returns_none_for_unknown_cpu(self) -> None:
        installer = self._make_installer()
        with patch("pathlib.Path.read_text", return_value="flags: SomeFutureCPU fpu"):
            assert installer._detect_microcode_package() is None

    def test_returns_none_on_oserror(self) -> None:
        installer = self._make_installer()
        with patch("pathlib.Path.read_text", side_effect=OSError("no access")):
            assert installer._detect_microcode_package() is None


# ---------------------------------------------------------------------------
# Installer._root_partition_device / _root_device_for_fstab
# ---------------------------------------------------------------------------


class TestRootDeviceHelpers:
    def _make_installer(self, device: str = "/dev/sda", use_luks: bool = False) -> Installer:
        inst = Installer()
        inst.config.disk.device = device
        inst.config.disk.use_luks = use_luks
        inst.tui = None
        return inst

    def test_sata_disk_gets_suffix_2(self) -> None:
        installer = self._make_installer("/dev/sda")
        assert installer._root_partition_device() == "/dev/sda2"

    def test_virtio_disk_gets_suffix_2(self) -> None:
        installer = self._make_installer("/dev/vda")
        assert installer._root_partition_device() == "/dev/vda2"

    def test_nvme_disk_gets_p2_suffix(self) -> None:
        installer = self._make_installer("/dev/nvme0n1")
        assert installer._root_partition_device() == "/dev/nvme0n1p2"

    def test_mmcblk_disk_gets_p2_suffix(self) -> None:
        installer = self._make_installer("/dev/mmcblk0")
        assert installer._root_partition_device() == "/dev/mmcblk0p2"

    def test_fstab_device_no_luks(self) -> None:
        installer = self._make_installer("/dev/sda", use_luks=False)
        assert installer._root_device_for_fstab() == "/dev/sda2"

    def test_fstab_device_with_luks(self) -> None:
        installer = self._make_installer("/dev/sda", use_luks=True)
        assert installer._root_device_for_fstab() == "/dev/mapper/ouroboros-root"


# ---------------------------------------------------------------------------
# Installer._update_progress
# ---------------------------------------------------------------------------


class TestUpdateProgress:
    def test_with_tui_calls_update(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        installer.tui = mock_tui
        installer._update_progress(State.INSTALL, 50, "Testing")
        mock_tui.update_install_progress.assert_called_once()

    def test_without_tui_no_error(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress(State.INSTALL, 50, "Testing")  # Must not raise


# ---------------------------------------------------------------------------
# Installer._run_op
# ---------------------------------------------------------------------------


class TestRunOp:
    def test_success_does_not_raise(self) -> None:
        installer = Installer()
        installer.tui = None
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line 1\n", "line 2\n"])
        mock_proc.returncode = 0
        mock_proc.__enter__ = lambda s: s
        mock_proc.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.Popen", return_value=mock_proc):
            installer._run_op(["echo", "hello"], final_msg="done")

    def test_failure_raises_installer_error(self) -> None:
        installer = Installer()
        installer.tui = None
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 1
        mock_proc.__enter__ = lambda s: s
        mock_proc.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.Popen", return_value=mock_proc):
            with pytest.raises(InstallerError, match="Operation failed"):
                installer._run_op(["false"])


# ---------------------------------------------------------------------------
# Installer._check_network
# ---------------------------------------------------------------------------


class TestCheckNetwork:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst.tui = None
        return inst

    def test_passes_when_ping_succeeds(self) -> None:
        installer = self._make_installer()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            installer._check_network()  # must not raise

    def test_raises_when_ping_fails_no_tui(self) -> None:
        installer = self._make_installer()
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(InstallerError, match="No internet"):
                installer._check_network()

    def test_with_tui_wifi_connect_success(self) -> None:
        installer = self._make_installer()
        mock_tui = MagicMock()
        mock_tui.show_wifi_connect.return_value = True
        installer.tui = mock_tui

        ping_fail = MagicMock()
        ping_fail.returncode = 1
        ping_ok = MagicMock()
        ping_ok.returncode = 0

        with patch("subprocess.run", side_effect=[ping_fail, ping_ok]):
            installer._check_network()  # must not raise

    def test_with_tui_wifi_connect_then_still_no_net(self) -> None:
        installer = self._make_installer()
        mock_tui = MagicMock()
        mock_tui.show_wifi_connect.return_value = True
        installer.tui = mock_tui

        ping_fail = MagicMock()
        ping_fail.returncode = 1

        with patch("subprocess.run", return_value=ping_fail):
            with pytest.raises(InstallerError, match="No internet"):
                installer._check_network()


# ---------------------------------------------------------------------------
# Installer._generate_mirrorlist
# ---------------------------------------------------------------------------


class TestGenerateMirrorlist:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst.tui = None
        return inst

    def test_regional_reflector_success(self) -> None:
        installer = self._make_installer()
        installer._update_progress = MagicMock()
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", return_value=ok):
            installer._generate_mirrorlist()  # must not raise

    def test_regional_fail_global_success(self) -> None:
        installer = self._make_installer()
        installer._update_progress = MagicMock()
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "timeout"
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", side_effect=[fail, ok]):
            installer._generate_mirrorlist()  # must not raise

    def test_both_reflector_calls_fail_raises(self) -> None:
        installer = self._make_installer()
        installer._update_progress = MagicMock()
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "timeout"
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(InstallerError, match="reflector"):
                installer._generate_mirrorlist()


# ---------------------------------------------------------------------------
# Installer._init_pacman_keyring
# ---------------------------------------------------------------------------


class TestInitPacmanKeyring:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst.tui = None
        inst._update_progress = MagicMock()
        return inst

    def test_success(self) -> None:
        installer = self._make_installer()
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", return_value=ok):
            installer._init_pacman_keyring()  # must not raise

    def test_init_step_fails_raises(self) -> None:
        installer = self._make_installer()
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "error"
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(InstallerError, match="pacman-key"):
                installer._init_pacman_keyring()


# ---------------------------------------------------------------------------
# Installer._handle_init
# ---------------------------------------------------------------------------


class TestHandleInit:
    def test_unattended_mode_loads_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "disk:\n  device: /dev/vda\n"
            "user:\n  username: testuser\n"
        )
        installer = Installer(config_path=config_file)
        mock_config = MagicMock()
        with patch("installer.state_machine.load_config", return_value=mock_config):
            installer._handle_init()
        assert installer.tui is None
        assert installer.config is mock_config

    def test_interactive_mode_creates_tui(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        with patch("installer.state_machine.find_unattended_config", return_value=None), \
             patch("installer.state_machine.TUI", return_value=mock_tui):
            installer._handle_init()
        assert installer.tui is mock_tui
        mock_tui.show_welcome.assert_called_once()

    def test_remote_config_downloads_and_loads(self, tmp_path: Path) -> None:
        """INIT: remote URL prompt → download → unattended mode."""
        installer = Installer()
        mock_tui = MagicMock()
        mock_tui.show_remote_config_prompt.return_value = "https://example.com/config.yaml"
        mock_config = MagicMock()

        with patch("installer.state_machine.find_unattended_config", return_value=None), \
             patch("installer.state_machine.TUI", return_value=mock_tui), \
             patch("installer.state_machine.load_config_from_url", return_value=mock_config) as mock_load:
            installer._handle_init()

        assert installer.tui is None  # switched to unattended
        assert installer.config is mock_config
        mock_tui.show_remote_config_prompt.assert_called_once()
        mock_load.assert_called_once_with("https://example.com/config.yaml")

    def test_remote_config_declined_continues_interactive(self) -> None:
        """INIT: user declines remote config → interactive mode."""
        installer = Installer()
        mock_tui = MagicMock()
        mock_tui.show_remote_config_prompt.return_value = None

        with patch("installer.state_machine.find_unattended_config", return_value=None), \
             patch("installer.state_machine.TUI", return_value=mock_tui):
            installer._handle_init()

        assert installer.tui is mock_tui  # still interactive
        mock_tui.show_remote_config_prompt.assert_called_once()

    def test_remote_config_download_fails_falls_through(self) -> None:
        """INIT: download fails → fall back to interactive mode."""
        installer = Installer()
        mock_tui = MagicMock()
        mock_tui.show_remote_config_prompt.return_value = "https://example.com/bad.yaml"
        mock_error = Exception("Network error")

        with patch("installer.state_machine.find_unattended_config", return_value=None), \
             patch("installer.state_machine.TUI", return_value=mock_tui), \
             patch("installer.state_machine.load_config_from_url", side_effect=mock_error):
            installer._handle_init()

        assert installer.tui is mock_tui  # still interactive despite error
        mock_tui.show_error.assert_called_once()
        expected_error_msg = f"Failed to load remote config:\n{mock_error}\n\nContinuing in interactive mode."
        mock_tui.show_error.assert_called_once_with(expected_error_msg, recoverable=True)


# ---------------------------------------------------------------------------
# Installer._handle_locale
# ---------------------------------------------------------------------------


class TestHandleLocale:
    def test_unattended_uses_default_config(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        installer._handle_locale()  # must not raise, config stays as default
        assert installer.config.locale.locale  # non-empty

    def test_tui_mode_updates_config(self) -> None:
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_locale_menu.return_value = {
            "locale": "es_AR.UTF-8",
            "keymap": "la-latin1",
            "timezone": "America/Argentina/Buenos_Aires",
        }
        mock_tui.show_hostname_input.return_value = "mi-maquina"
        installer.tui = mock_tui
        installer._handle_locale()
        assert installer.config.locale.locale == "es_AR.UTF-8"
        assert installer.config.network.hostname == "mi-maquina"


# ---------------------------------------------------------------------------
# Installer._handle_partition
# ---------------------------------------------------------------------------


class TestHandlePartition:
    def test_unattended_skips_tui(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        installer.config.disk.device = "/dev/vda"
        installer._handle_partition()  # must not raise

    def test_tui_confirmed_sets_disk(self) -> None:
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_disk_selection.return_value = "/dev/sda"
        mock_tui.show_luks_prompt.return_value = False
        mock_tui.show_confirmation.return_value = True
        installer.tui = mock_tui
        installer._handle_partition()
        assert installer.config.disk.device == "/dev/sda"

    def test_tui_user_aborts_raises(self) -> None:
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_disk_selection.return_value = "/dev/sda"
        mock_tui.show_luks_prompt.return_value = False
        mock_tui.show_confirmation.return_value = False
        installer.tui = mock_tui
        with pytest.raises(InstallerError, match="did not confirm"):
            installer._handle_partition()

    def test_tui_luks_prompts_for_passphrase(self) -> None:
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_disk_selection.return_value = "/dev/sda"
        mock_tui.show_luks_prompt.return_value = True
        mock_tui.show_passphrase_input.return_value = "s3cr3t"
        mock_tui.show_confirmation.return_value = True
        installer.tui = mock_tui
        installer._handle_partition()
        assert installer.config.disk.use_luks is True
        assert installer.config.disk.luks_passphrase == "s3cr3t"


# ---------------------------------------------------------------------------
# Installer._handle_format
# ---------------------------------------------------------------------------


class TestHandleFormat:
    def test_calls_run_op_with_disk_args(self) -> None:
        installer = Installer()
        installer.tui = None
        installer.config.disk.device = "/dev/vda"
        installer._update_progress = MagicMock()
        with patch.object(installer, "_run_op") as mock_run:
            installer._handle_format()
        args_called = mock_run.call_args[0][0]
        assert "prepare_disk" in args_called
        assert "/dev/vda" in args_called

    def test_luks_passphrase_cleared_after_format(self) -> None:
        installer = Installer()
        installer.tui = None
        installer.config.disk.device = "/dev/vda"
        installer.config.disk.use_luks = True
        installer.config.disk.luks_passphrase = "s3cr3t"
        installer._update_progress = MagicMock()
        with patch.object(installer, "_run_op"):
            installer._handle_format()
        assert installer.config.disk.luks_passphrase == ""


# ---------------------------------------------------------------------------
# Installer._handle_configure
# ---------------------------------------------------------------------------


class TestHandleConfigure:
    def test_success(self, tmp_path: Path) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        installer.config.disk.device = "/dev/vda"
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", return_value=ok), \
             patch("installer.state_machine.OPS_DIR", tmp_path):
            installer._handle_configure()

    def test_failure_raises_installer_error(self, tmp_path: Path) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        installer.config.disk.device = "/dev/vda"
        fail = MagicMock()
        fail.returncode = 1
        with patch("subprocess.run", return_value=fail), \
             patch("installer.state_machine.OPS_DIR", tmp_path):
            with pytest.raises(InstallerError, match="configuration failed"):
                installer._handle_configure()

    def test_configure_no_longer_prompts_user(self, tmp_path: Path) -> None:
        """Phase 2: _handle_configure must NOT call show_user_creation.

        User prompt was moved to _handle_user, which runs before PARTITION,
        so the disk wipe can't happen on a cancelled user prompt.
        """
        installer = Installer()
        installer._update_progress = MagicMock()
        installer.config.disk.device = "/dev/vda"
        installer.config.user.username = "prefilled"
        installer.config.user.password_hash = "$6$xxx"
        mock_tui = MagicMock()
        installer.tui = mock_tui
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", return_value=ok), \
             patch("installer.state_machine.OPS_DIR", tmp_path):
            installer._handle_configure()
        mock_tui.show_user_creation.assert_not_called()
        assert installer.config.user.username == "prefilled"

    def test_handle_user_prompts_before_disk_touch(self) -> None:
        """Phase 2: _handle_user collects credentials pre-wipe."""
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_user_creation.return_value = {
            "username": "testuser",
            "password_hash": "$6$xxx",
        }
        mock_tui.show_shell_selection.return_value = "bash"
        installer.tui = mock_tui
        installer._handle_user()
        assert installer.config.user.username == "testuser"
        assert installer.config.user.password_hash == "$6$xxx"
        assert installer.config.user.shell == "/bin/bash"

    def test_handle_desktop_sets_profile(self) -> None:
        """Phase 2: _handle_desktop stores the selected profile and DM."""
        installer = Installer()
        installer._update_progress = MagicMock()
        mock_tui = MagicMock()
        mock_tui.show_desktop_selection.return_value = "hyprland"
        mock_tui.show_dm_selection.return_value = "auto"
        installer.tui = mock_tui
        installer._handle_desktop()
        assert installer.config.desktop.profile == "hyprland"
        assert installer.config.desktop.dm == "auto"

    def test_user_state_runs_before_partition(self) -> None:
        """Phase 2: USER and DESKTOP must come before PARTITION in _STATE_ORDER."""
        from installer.state_machine import _STATE_ORDER, State
        order = _STATE_ORDER
        assert order.index(State.USER) < order.index(State.PARTITION)
        assert order.index(State.DESKTOP) < order.index(State.PARTITION)
        assert order.index(State.USER) < order.index(State.FORMAT)


# ---------------------------------------------------------------------------
# Installer._handle_snapshot
# ---------------------------------------------------------------------------


class TestHandleSnapshot:
    def test_success(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        ok = MagicMock()
        ok.returncode = 0
        with patch("subprocess.run", return_value=ok):
            installer._handle_snapshot()  # must not raise

    def test_failure_only_warns(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        fail = MagicMock()
        fail.returncode = 1
        with patch("subprocess.run", return_value=fail):
            installer._handle_snapshot()  # must NOT raise — only warns


# ---------------------------------------------------------------------------
# Installer._handle_finish
# ---------------------------------------------------------------------------


class TestHandleFinish:
    def _make_installer(self, action: str = "none") -> Installer:
        inst = Installer()
        inst.tui = None
        inst.config.post_install_action = action
        return inst

    def test_action_none_stays_up(self) -> None:
        installer = self._make_installer("none")
        with patch("os.system") as mock_system:
            installer._handle_finish()
        mock_system.assert_not_called()

    def test_action_shutdown_calls_poweroff(self) -> None:
        installer = self._make_installer("shutdown")
        with patch("os.system") as mock_system:
            installer._handle_finish()
        mock_system.assert_called_once_with("poweroff")

    def test_action_reboot_calls_reboot(self) -> None:
        installer = self._make_installer("reboot")
        with patch("os.system") as mock_system:
            installer._handle_finish()
        mock_system.assert_called_once_with("reboot")

    def test_tui_mode_shows_summary(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        mock_tui.show_post_install_action.return_value = "none"
        installer.tui = mock_tui
        with patch("os.system"):
            installer._handle_finish()
        mock_tui.finish_install_progress.assert_called_once()
        mock_tui.show_summary.assert_called_once()


# ---------------------------------------------------------------------------
# Installer._handle_preflight
# ---------------------------------------------------------------------------


class TestHandlePreflight:
    def test_all_checks_pass(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        with patch.object(installer, "_check_uefi"), \
             patch.object(installer, "_check_root"), \
             patch.object(installer, "_check_tools"), \
             patch.object(installer, "_check_ram"), \
             patch.object(installer, "_check_network"):
            installer._handle_preflight()  # must not raise

    def test_failed_check_raises_installer_error(self) -> None:
        installer = Installer()
        installer.tui = None
        installer._update_progress = MagicMock()
        with patch.object(installer, "_check_uefi", side_effect=InstallerError("no UEFI")), \
             patch.object(installer, "_check_root"), \
             patch.object(installer, "_check_tools"), \
             patch.object(installer, "_check_ram"), \
             patch.object(installer, "_check_network"):
            with pytest.raises(InstallerError, match="Preflight checks failed"):
                installer._handle_preflight()


# ---------------------------------------------------------------------------
# Installer run() — TUI fatal + keyboard interrupt with TUI
# ---------------------------------------------------------------------------


class TestInstallerRunWithTUI:
    def test_fatal_error_with_tui_shows_error(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        installer.tui = mock_tui
        installer._handler_map[State.INIT] = MagicMock(side_effect=FatalError("boom"))
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1
        mock_tui.stop_install_progress.assert_called()
        mock_tui.show_error.assert_called()

    def test_keyboard_interrupt_with_tui_shows_error(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        installer.tui = mock_tui
        installer._handler_map[State.INIT] = MagicMock(side_effect=KeyboardInterrupt)
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1
        mock_tui.stop_install_progress.assert_called()

    def test_tui_user_chooses_abort_on_recoverable_error(self) -> None:
        installer = Installer()
        mock_tui = MagicMock()
        mock_tui.show_error.return_value = False  # User chooses abort
        installer.tui = mock_tui
        installer._handler_map[State.INIT] = MagicMock(
            side_effect=InstallerError("oops")
        )
        with patch("installer.state_machine._save_checkpoint"):
            result = installer.run()
        assert result == 1


# ---------------------------------------------------------------------------
# _handle_user — password_plaintext + shell package
# ---------------------------------------------------------------------------


class TestHandleUser:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst._update_progress = MagicMock()
        return inst

    def test_password_plaintext_set_from_tui(self) -> None:
        installer = self._make_installer()
        mock_tui = MagicMock()
        mock_tui.show_user_creation.return_value = {
            "username": "alice",
            "password_hash": "$6$hash",
            "password": "plaintext123",
        }
        mock_tui.show_shell_selection.return_value = "bash"
        installer.tui = mock_tui
        installer._handle_user()
        assert installer.config.user.password_plaintext == "plaintext123"

    def test_non_base_shell_queued_as_extra_package(self) -> None:
        installer = self._make_installer()
        mock_tui = MagicMock()
        mock_tui.show_user_creation.return_value = {
            "username": "alice",
            "password_hash": "$6$hash",
        }
        mock_tui.show_shell_selection.return_value = "fish"
        installer.tui = mock_tui
        installer._handle_user()
        assert "fish" in installer.config.extra_packages

    def test_extra_package_not_duplicated(self) -> None:
        installer = self._make_installer()
        installer.config.extra_packages = ["fish"]
        mock_tui = MagicMock()
        mock_tui.show_user_creation.return_value = {
            "username": "alice",
            "password_hash": "$6$hash",
        }
        mock_tui.show_shell_selection.return_value = "fish"
        installer.tui = mock_tui
        installer._handle_user()
        assert installer.config.extra_packages.count("fish") == 1


# ---------------------------------------------------------------------------
# _handle_secure_boot — enabled branch
# ---------------------------------------------------------------------------


class TestHandleSecureBoot:
    def _make_installer(self) -> Installer:
        inst = Installer()
        inst._update_progress = MagicMock()
        return inst

    def test_skipped_when_disabled(self) -> None:
        installer = self._make_installer()
        installer.config.security.secure_boot = False
        installer.tui = MagicMock()
        installer._handle_secure_boot()
        installer.tui.show_secure_boot_prompt.assert_not_called()

    def test_shows_prompt_when_enabled(self) -> None:
        installer = self._make_installer()
        installer.config.security.secure_boot = True
        mock_tui = MagicMock()
        installer.tui = mock_tui
        installer._handle_secure_boot()
        mock_tui.show_secure_boot_prompt.assert_called_once()

    def test_no_tui_with_secure_boot_enabled(self) -> None:
        installer = self._make_installer()
        installer.config.security.secure_boot = True
        installer.tui = None
        installer._handle_secure_boot()  # must not raise


# ---------------------------------------------------------------------------
# _check_ram — OSError branch
# ---------------------------------------------------------------------------


class TestCheckRam:
    def _make_installer(self) -> Installer:
        return Installer()

    def test_raises_when_ram_insufficient(self) -> None:
        installer = self._make_installer()
        meminfo = "MemTotal:         512000 kB\n"
        with patch("installer.state_machine.Path.read_text", return_value=meminfo):
            with pytest.raises(InstallerError, match="Insufficient RAM"):
                installer._check_ram()

    def test_passes_when_ram_sufficient(self) -> None:
        installer = self._make_installer()
        meminfo = "MemTotal:        4096000 kB\n"
        with patch("installer.state_machine.Path.read_text", return_value=meminfo):
            installer._check_ram()  # must not raise

    def test_oserror_reading_meminfo_treats_as_zero_ram(self) -> None:
        installer = self._make_installer()
        # OSError is silently caught but mem_kb stays 0 → InstallerError raised
        with patch("installer.state_machine.Path.read_text", side_effect=OSError("no file")):
            with pytest.raises(InstallerError, match="Insufficient RAM"):
                installer._check_ram()
