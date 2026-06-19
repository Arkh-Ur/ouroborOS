"""test_install_handler.py — Unit tests for Installer._handle_install() and helpers."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from installer.state_machine import Installer, InstallerError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_installer(tmp_path: Path) -> Installer:
    """Return an Installer with a minimal config and mocked TUI."""
    inst = Installer()
    inst.config.disk.device = "/dev/vda"
    inst.config.install_target = str(tmp_path / "mnt")
    inst.config.desktop.profile = "minimal"
    inst.config.desktop.dm = "none"
    inst.tui = None
    (tmp_path / "mnt" / "etc").mkdir(parents=True, exist_ok=True)
    return inst


def _success() -> CompletedProcess:
    return CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _failure(code: int = 1) -> CompletedProcess:
    return CompletedProcess(args=[], returncode=code, stdout="", stderr="")


def _mock_popen(returncode: int = 0, lines: list[str] | None = None) -> tuple:
    """Return (popen_cls_mock, proc_mock) for patching subprocess.Popen."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = iter(lines or [])
    # communicate() returns (stdout, stderr); unpacking requires a proper 2-tuple
    proc.communicate.return_value = ("\n".join(lines or []), None)
    proc.__enter__ = lambda s: s
    proc.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=proc), proc


# ---------------------------------------------------------------------------
# _handle_install — happy path
# ---------------------------------------------------------------------------


class TestHandleInstallHappyPath:
    @pytest.fixture(autouse=True)
    def _mock_internet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from installer import state_machine  # noqa: PLC0415
        monkeypatch.setattr(state_machine.Installer, "_has_internet", lambda self: True)
    def test_pacstrap_called_with_base_packages(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        popen_cls, _ = _mock_popen()

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls) as mock_popen:
            inst._handle_install()

        calls = [str(c) for c in mock_popen.call_args_list]
        assert any("pacstrap" in c for c in calls)

    def test_mkinitcpio_conf_written_before_pacstrap(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        mkinitcpio = Path(inst.config.install_target) / "etc" / "mkinitcpio.conf"
        popen_cls, _ = _mock_popen()

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls):
            inst._handle_install()

        assert mkinitcpio.exists()
        content = mkinitcpio.read_text()
        assert "btrfs" in content
        assert "MODULES" in content

    def test_microcode_prepended_to_package_list(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        popen_cls, _ = _mock_popen()

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value="amd-ucode"), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls) as mock_popen:
            inst._handle_install()

        pacstrap_call = None
        for c in mock_popen.call_args_list:
            args = c.args[0] if c.args else []
            if args and args[0] == "pacstrap":
                pacstrap_call = args
                break

        assert pacstrap_call is not None
        assert "amd-ucode" in pacstrap_call

    def test_extra_packages_included(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        inst.config.extra_packages = ["neovim", "tmux"]
        popen_cls, _ = _mock_popen()

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls) as mock_popen:
            inst._handle_install()

        pacstrap_call = mock_popen.call_args_list[0].args[0]
        assert "neovim" in pacstrap_call
        assert "tmux" in pacstrap_call

    def test_regenerate_fstab_called_after_pacstrap(self, tmp_path: Path) -> None:
        call_order: list[str] = []

        inst = _make_installer(tmp_path)

        def fake_popen(cmd: list[str], **kwargs: object) -> MagicMock:
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = iter([])
            proc.communicate.return_value = ("", None)
            proc.__enter__ = lambda s: s
            proc.__exit__ = MagicMock(return_value=False)
            if cmd and cmd[0] == "pacstrap":
                call_order.append("pacstrap")
            return proc

        def fake_fstab() -> None:
            call_order.append("fstab")

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab", side_effect=fake_fstab), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", side_effect=fake_popen):
            inst._handle_install()

        assert call_order.index("pacstrap") < call_order.index("fstab")


# ---------------------------------------------------------------------------
# _handle_install — retry logic
# ---------------------------------------------------------------------------


class TestHandleInstallRetry:
    @pytest.fixture(autouse=True)
    def _mock_internet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from installer import state_machine  # noqa: PLC0415
        monkeypatch.setattr(state_machine.Installer, "_has_internet", lambda self: True)

    def test_retries_on_failure_then_succeeds(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        call_count = 0

        def flaky_popen(cmd: list[str], **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            proc.returncode = 1 if call_count < 3 else 0
            proc.stdout = iter([])
            proc.communicate.return_value = ("", None)
            proc.__enter__ = lambda s: s
            proc.__exit__ = MagicMock(return_value=False)
            return proc

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", side_effect=flaky_popen):
            inst._handle_install()

        assert call_count == 3

    def test_raises_after_max_retries(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.run", return_value=_failure()):
            with pytest.raises(InstallerError, match="pacstrap failed"):
                inst._handle_install()

    def test_mirrorlist_regenerated_on_retry(self, tmp_path: Path) -> None:
        inst = _make_installer(tmp_path)
        mirror_calls = 0

        def count_mirror() -> None:
            nonlocal mirror_calls
            mirror_calls += 1

        call_count = 0

        def flaky_popen(cmd: list[str], **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            proc.returncode = 1 if call_count < 2 else 0
            proc.stdout = iter([])
            proc.communicate.return_value = ("", None)
            proc.__enter__ = lambda s: s
            proc.__exit__ = MagicMock(return_value=False)
            return proc

        with patch.object(inst, "_generate_mirrorlist", side_effect=count_mirror), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", side_effect=flaky_popen):
            inst._handle_install()

        # Called once at start + once on retry = 2
        assert mirror_calls >= 2


# ---------------------------------------------------------------------------
# _handle_install — stdout logging and non-none DM
# ---------------------------------------------------------------------------


class TestHandleInstallEdgeCases:
    @pytest.fixture(autouse=True)
    def _mock_internet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from installer import state_machine  # noqa: PLC0415
        monkeypatch.setattr(state_machine.Installer, "_has_internet", lambda self: True)

    def test_pacstrap_stdout_logged(self, tmp_path: Path) -> None:
        """Covers the stdout-logging block (lines 644-648)."""
        inst = _make_installer(tmp_path)
        popen_cls, _ = _mock_popen(
            returncode=0,
            lines=[":: Syncing package databases...\n", "  warning: something\n"],
        )

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls):
            inst._handle_install()  # must not raise

    def test_dm_package_appended_for_sddm(self, tmp_path: Path) -> None:
        """Covers lines 613-615: DM package added when DM is not 'none'."""
        inst = _make_installer(tmp_path)
        inst.config.desktop.profile = "hyprland"
        inst.config.desktop.dm = "sddm"
        popen_cls, _ = _mock_popen()

        with patch.object(inst, "_generate_mirrorlist"), \
             patch.object(inst, "_init_pacman_keyring"), \
             patch.object(inst, "_detect_microcode_package", return_value=None), \
             patch.object(inst, "_regenerate_fstab"), \
             patch.object(inst, "_update_progress"), \
             patch("installer.state_machine.subprocess.Popen", popen_cls) as mock_popen:
            inst._handle_install()

        pacstrap_args = mock_popen.call_args_list[0].args[0]
        assert "sddm" in pacstrap_args


# ---------------------------------------------------------------------------
# _regenerate_fstab — direct unit test
# ---------------------------------------------------------------------------


class TestRegenerateFstab:
    def test_regenerate_fstab_calls_run_op(self, tmp_path: Path) -> None:
        """Covers lines 697-709: _regenerate_fstab builds correct args."""
        inst = _make_installer(tmp_path)
        inst.config.disk.device = "/dev/vda"

        run_op_calls: list = []

        def fake_run_op(args: list[str], **kwargs):
            run_op_calls.append(args)

        with patch.object(inst, "_root_device_for_fstab", return_value="/dev/vda2"), \
             patch.object(inst, "_run_op", side_effect=fake_run_op):
            inst._regenerate_fstab()

        assert len(run_op_calls) == 1
        args = run_op_calls[0]
        assert "--action" in args
        assert "regenerate_fstab" in args
        assert "--target" in args
        assert "--root-device" in args
        assert "/dev/vda2" in args


# ---------------------------------------------------------------------------
# _which() — static method unit test
# ---------------------------------------------------------------------------


class TestWhich:
    def test_which_returns_true_for_existing_tool(self) -> None:
        """Covers lines 877-878: _which() uses shutil.which."""
        # 'bash' is always available in the test environment
        assert Installer._which("bash") is True

    def test_which_returns_false_for_missing_tool(self) -> None:
        assert Installer._which("this-tool-definitely-does-not-exist-xyz") is False
