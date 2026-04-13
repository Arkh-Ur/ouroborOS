"""test_tui.py — Tests for the TUI module."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from installer.tui import TUI, TUIError, _hash_password, _lsblk_disks, _whiptail

RICH_PATCHES = [
    "installer.tui.Console",
    "installer.tui.Panel",
    "installer.tui.Confirm",
    "installer.tui.IntPrompt",
    "installer.tui.Prompt",
    "installer.tui.Table",
    "installer.tui.Text",
]


@contextmanager
def _patch_rich():
    mocks = {name.split(".")[-1]: MagicMock() for name in RICH_PATCHES}
    patches = [patch(name, mocks[name.split(".")[-1]]) for name in RICH_PATCHES]
    patches.append(patch("installer.tui.HAS_RICH", True))
    for p in patches:
        p.start()
    try:
        yield mocks
    finally:
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rich_tui() -> TUI:
    with _patch_rich() as mocks:
        tui = TUI(title="Test Installer")
        tui._console = mocks["Console"].return_value
        yield tui


@pytest.fixture()
def whiptail_tui() -> TUI:
    with patch("installer.tui.HAS_RICH", False), patch(
        "installer.tui.shutil.which", return_value="/usr/bin/whiptail"
    ):
        yield TUI(title="Test Installer")


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


class TestBackendSelection:
    def test_rich_backend_when_available(self) -> None:
        with _patch_rich():
            tui = TUI(title="Test")
            assert tui._backend == "rich"

    def test_whiptail_fallback_when_rich_missing(self) -> None:
        with patch("installer.tui.HAS_RICH", False), patch(
            "installer.tui.shutil.which", return_value="/usr/bin/whiptail"
        ):
            tui = TUI(title="Test")
            assert tui._backend == "whiptail"

    def test_raises_when_neither_available(self) -> None:
        with patch("installer.tui.HAS_RICH", False), patch(
            "installer.tui.shutil.which", return_value=None
        ):
            with pytest.raises(TUIError, match="Neither rich nor whiptail"):
                TUI(title="Test")


# ---------------------------------------------------------------------------
# _whiptail wrapper (backend-independent utility)
# ---------------------------------------------------------------------------


class TestWhiptailWrapper:
    def test_returns_returncode_and_stderr(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = "selected_item"
        with patch(
            "installer.tui._get_whiptail_path", return_value="/usr/bin/whiptail"
        ), patch("installer.tui.subprocess.run", return_value=mock_result):
            rc, output = _whiptail("--msgbox", "hello", "10", "40")
        assert rc == 0
        assert output == "selected_item"

    def test_cancel_returns_nonzero_rc(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        with patch(
            "installer.tui._get_whiptail_path", return_value="/usr/bin/whiptail"
        ), patch("installer.tui.subprocess.run", return_value=mock_result):
            rc, _ = _whiptail("--msgbox", "bye", "10", "40")
        assert rc == 1


# ---------------------------------------------------------------------------
# _lsblk_disks (backend-independent)
# ---------------------------------------------------------------------------


class TestLsblkDisks:
    def test_parses_lsblk_json(self) -> None:
        lsblk_output = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "sda",
                        "size": "500G",
                        "model": "Samsung SSD",
                        "type": "disk",
                        "hotplug": False,
                    },
                    {
                        "name": "sda1",
                        "size": "512M",
                        "model": None,
                        "type": "part",
                        "hotplug": False,
                    },
                ]
            }
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = lsblk_output
        with patch("installer.tui.subprocess.run", return_value=mock_result):
            disks = _lsblk_disks()
        assert len(disks) == 1
        assert disks[0]["name"] == "/dev/sda"
        assert disks[0]["size"] == "500G"

    def test_returns_empty_on_lsblk_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("installer.tui.subprocess.run", return_value=mock_result):
            disks = _lsblk_disks()
        assert disks == []

    def test_returns_empty_on_invalid_json(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        with patch("installer.tui.subprocess.run", return_value=mock_result):
            disks = _lsblk_disks()
        assert disks == []


# ---------------------------------------------------------------------------
# _hash_password (backend-independent)
# ---------------------------------------------------------------------------


class TestHashPassword:
    def test_hash_starts_with_sha512_marker(self) -> None:
        hashed = _hash_password("mypassword")
        assert hashed.startswith("$6$")

    def test_same_password_different_salt(self) -> None:
        h1 = _hash_password("password")
        h2 = _hash_password("password")
        assert h1 != h2

    def test_hash_is_verifiable(self) -> None:
        import subprocess

        password = "testpass123"
        hashed = _hash_password(password)
        salt = hashed.split("$")[2]
        result = subprocess.run(
            ["openssl", "passwd", "-6", "-salt", salt, password],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == hashed


# ---------------------------------------------------------------------------
# Rich backend tests
# ---------------------------------------------------------------------------


class TestRichShowWelcome:
    def test_prints_panel(self, rich_tui: TUI) -> None:
        with _patch_rich():
            rich_tui.show_welcome()
        rich_tui._console.print.assert_called()


class TestRichShowProgress:
    def test_creates_progress(self, rich_tui: TUI) -> None:
        rich_tui._console = MagicMock()
        rich_tui.show_progress("Test", "Working...", 50)
        rich_tui._console.print.assert_called()

    def test_stops_at_100(self, rich_tui: TUI) -> None:
        rich_tui._console = MagicMock()
        rich_tui.show_progress("Test", "Done!", 100)
        assert rich_tui._progress_title == ""

    def test_updates_existing_progress(self, rich_tui: TUI) -> None:
        rich_tui._console = MagicMock()
        rich_tui.show_progress("Test", "Working...", 50)
        rich_tui.show_progress("Test", "Still working...", 75)
        assert rich_tui._console.print.call_count == 2


class TestGlobalInstallProgress:
    def test_start_sets_active(self, rich_tui: TUI) -> None:
        rich_tui.start_install_progress()
        assert rich_tui._install_progress_active is True
        assert rich_tui._install_progress_pct == 0

    def test_update_sets_pct_and_active(self, rich_tui: TUI) -> None:
        rich_tui.update_install_progress(35, 3, 9, "Preparando disco", "Particionando...")
        assert rich_tui._install_progress_active is True
        assert rich_tui._install_progress_pct == 35

    def test_update_clamps_percent(self, rich_tui: TUI) -> None:
        rich_tui.update_install_progress(-10, 1, 9, "Test")
        assert rich_tui._install_progress_pct == 0
        rich_tui.update_install_progress(150, 1, 9, "Test")
        assert rich_tui._install_progress_pct == 100

    def test_stop_clears_active(self, rich_tui: TUI) -> None:
        rich_tui.start_install_progress()
        rich_tui.update_install_progress(50, 3, 9, "Test")
        rich_tui.stop_install_progress()
        assert rich_tui._install_progress_active is False

    def test_stop_noop_when_inactive(self, rich_tui: TUI) -> None:
        rich_tui.stop_install_progress()
        assert rich_tui._install_progress_active is False

    def test_finish_sets_100_and_clears(self, rich_tui: TUI) -> None:
        rich_tui.start_install_progress()
        rich_tui.update_install_progress(50, 3, 9, "Test")
        rich_tui.finish_install_progress()
        assert rich_tui._install_progress_pct == 100
        assert rich_tui._install_progress_active is False

    def test_update_resumes_after_stop(self, rich_tui: TUI) -> None:
        rich_tui.start_install_progress()
        rich_tui.stop_install_progress()
        assert rich_tui._install_progress_active is False
        rich_tui.update_install_progress(60, 4, 9, "Test")
        assert rich_tui._install_progress_active is True
        assert rich_tui._install_progress_pct == 60

    def test_stop_progress_also_clears_global(self, rich_tui: TUI) -> None:
        rich_tui.start_install_progress()
        rich_tui.update_install_progress(50, 3, 9, "Test")
        rich_tui._stop_progress()
        assert rich_tui._install_progress_active is False


class TestRichShowError:
    def test_recoverable_yes_returns_true(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = True
            assert rich_tui.show_error("Oops", recoverable=True) is True

    def test_recoverable_no_returns_false(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = False
            assert rich_tui.show_error("Oops", recoverable=True) is False

    def test_fatal_returns_false(self, rich_tui: TUI) -> None:
        with _patch_rich():
            assert rich_tui.show_error("Fatal!", recoverable=False) is False


class TestRichShowConfirmation:
    def test_yes_returns_true(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = True
            assert rich_tui.show_confirmation("Sure?") is True

    def test_no_returns_false(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = False
            assert rich_tui.show_confirmation("Sure?") is False


class TestRichShowLuksPrompt:
    def test_yes_returns_true(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = True
            assert rich_tui.show_luks_prompt() is True

    def test_no_returns_false(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Confirm"].ask.return_value = False
            assert rich_tui.show_luks_prompt() is False


class TestRichShowLocaleMenu:
    def test_returns_locale_dict(self, rich_tui: TUI) -> None:
        with (
            patch.object(
                rich_tui, "_rich_select", side_effect=["en_US.UTF-8", "us"]
            ),
            patch.object(rich_tui, "_rich_input", return_value="UTC"),
        ):
            result = rich_tui.show_locale_menu()
        assert result["locale"] == "en_US.UTF-8"
        assert result["keymap"] == "us"
        assert result["timezone"] == "UTC"


class TestRichShowHostnameInput:
    def test_returns_hostname(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Prompt"].ask.return_value = "myhost"
            assert rich_tui.show_hostname_input() == "myhost"


class TestRichShowDiskSelection:
    def test_returns_selected_disk(self, rich_tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "500G", "model": "SAMSUNG"}]
        with patch(
            "installer.tui._lsblk_disks", return_value=disks
        ), patch.object(rich_tui, "_rich_select", return_value="/dev/sda"):
            with _patch_rich():
                assert rich_tui.show_disk_selection() == "/dev/sda"

    def test_raises_when_no_disks(self, rich_tui: TUI) -> None:
        with patch("installer.tui._lsblk_disks", return_value=[]):
            with pytest.raises(TUIError, match="No suitable"):
                rich_tui.show_disk_selection()


class TestRichShowUserCreation:
    def test_successful_creation(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Prompt"].ask.side_effect = [
                "alice",
                "password123",
                "password123",
            ]
            result = rich_tui.show_user_creation()
        assert result["username"] == "alice"
        assert result["password_hash"].startswith("$6$")

    def test_password_mismatch_raises(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Prompt"].ask.side_effect = [
                "bob",
                "pass1",
                "pass2",
                "pass1",
                "pass2",
                "pass1",
                "pass2",
            ]
            with pytest.raises(TUIError, match="3 attempts"):
                rich_tui.show_user_creation()


class TestRichShowPassphraseInput:
    def test_matching_passphrases(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Prompt"].ask.side_effect = ["secure123", "secure123"]
            assert rich_tui.show_passphrase_input() == "secure123"

    def test_too_many_mismatches(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            mocks["Prompt"].ask.side_effect = ["a", "b", "c", "d", "e", "f"]
            with pytest.raises(TUIError, match="3 attempts"):
                rich_tui.show_passphrase_input()


class TestRichShowPartitionPreview:
    def test_prints_tables(self, rich_tui: TUI) -> None:
        with _patch_rich():
            rich_tui.show_partition_preview("/dev/sda", False)
        rich_tui._console.print.assert_called()


class TestRichShowSummary:
    def test_prints_summary(self, rich_tui: TUI) -> None:
        config = MagicMock()
        config.disk.device = "/dev/sda"
        config.disk.use_luks = False
        config.network.hostname = "test"
        config.user.username = "user"
        config.locale.locale = "en_US.UTF-8"
        config.locale.timezone = "UTC"
        with _patch_rich():
            rich_tui.show_summary(config)
        rich_tui._console.print.assert_called()


# ---------------------------------------------------------------------------
# Whiptail backend tests
# ---------------------------------------------------------------------------


class TestWhiptailCheckWhiptail:
    def test_raises_when_whiptail_missing(self) -> None:
        with patch("installer.tui.HAS_RICH", False), patch(
            "installer.tui.shutil.which", return_value=None
        ):
            with pytest.raises(TUIError, match="Neither rich nor whiptail"):
                TUI()


class TestWhiptailShowWelcome:
    def test_show_welcome_calls_whiptail(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail") as mock_wt:
            mock_wt.return_value = (0, "")
            whiptail_tui.show_welcome()
        mock_wt.assert_called_once()
        call_args = mock_wt.call_args[0]
        assert "--msgbox" in call_args


class TestWhiptailShowError:
    def test_recoverable_yes_returns_true(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert whiptail_tui.show_error("Oops", recoverable=True) is True

    def test_recoverable_no_returns_false(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert whiptail_tui.show_error("Oops", recoverable=True) is False

    def test_fatal_returns_false(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert whiptail_tui.show_error("Fatal!", recoverable=False) is False

    def test_fatal_uses_msgbox(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            whiptail_tui.show_error("Fatal!", recoverable=False)
        assert "--msgbox" in mock_wt.call_args[0]


class TestWhiptailShowConfirmation:
    def test_yes_returns_true(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert whiptail_tui.show_confirmation("Sure?") is True

    def test_no_returns_false(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert whiptail_tui.show_confirmation("Sure?") is False


class TestWhiptailShowDiskSelection:
    def test_returns_selected_disk(self, whiptail_tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "500G", "model": "SAMSUNG"}]
        with patch(
            "installer.tui._lsblk_disks", return_value=disks
        ), patch("installer.tui._whiptail", return_value=(0, "/dev/sda")):
            assert whiptail_tui.show_disk_selection() == "/dev/sda"

    def test_raises_when_no_disks(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._lsblk_disks", return_value=[]):
            with pytest.raises(TUIError, match="No suitable"):
                whiptail_tui.show_disk_selection()

    def test_raises_on_cancel(self, whiptail_tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "100G", "model": "Disk"}]
        with patch(
            "installer.tui._lsblk_disks", return_value=disks
        ), patch("installer.tui._whiptail", return_value=(1, "")):
            with pytest.raises(TUIError):
                whiptail_tui.show_disk_selection()


class TestWhiptailShowLocaleMenu:
    def test_returns_locale_dict(self, whiptail_tui: TUI) -> None:
        with (
            patch.object(
                whiptail_tui,
                "_select_from_list",
                side_effect=["en_US.UTF-8", "us"],
            ),
            patch.object(
                whiptail_tui, "_input_box", return_value="America/New_York"
            ),
        ):
            result = whiptail_tui.show_locale_menu()
        assert result["locale"] == "en_US.UTF-8"
        assert result["keymap"] == "us"
        assert result["timezone"] == "America/New_York"


class TestWhiptailShowUserCreation:
    def test_successful_user_creation(self, whiptail_tui: TUI) -> None:
        with (
            patch.object(whiptail_tui, "_input_box", return_value="alice"),
            patch.object(
                whiptail_tui,
                "_password_box",
                side_effect=["password123", "password123"],
            ),
        ):
            result = whiptail_tui.show_user_creation()
        assert result["username"] == "alice"
        assert result["password_hash"].startswith("$6$")

    def test_password_mismatch_retries(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui, "_input_box", return_value="bob"
        ), patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["p1", "p2", "p1", "p2", "p1", "p2"],
        ), patch.object(
            whiptail_tui, "show_error"
        ):
            with pytest.raises(TUIError, match="3 attempts"):
                whiptail_tui.show_user_creation()

    def test_short_password_retries(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui, "_input_box", return_value="carol"
        ), patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["hi", "hi", "validpassword", "validpassword"],
        ), patch.object(
            whiptail_tui, "show_error"
        ):
            result = whiptail_tui.show_user_creation()
        assert result["username"] == "carol"


class TestWhiptailShowLuks:
    def test_luks_yes(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert whiptail_tui.show_luks_prompt() is True

    def test_luks_no(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert whiptail_tui.show_luks_prompt() is False


class TestWhiptailPassphraseInput:
    def test_matching_passphrases(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["secure123", "secure123"],
        ):
            assert whiptail_tui.show_passphrase_input() == "secure123"

    def test_mismatch_then_match(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["wrong", "right", "correct!!", "correct!!"],
        ), patch.object(whiptail_tui, "show_error"):
            assert whiptail_tui.show_passphrase_input() == "correct!!"

    def test_short_passphrase_retries(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["abc", "abc", "longpassword", "longpassword"],
        ), patch.object(whiptail_tui, "show_error"):
            assert whiptail_tui.show_passphrase_input() == "longpassword"

    def test_too_many_mismatches(self, whiptail_tui: TUI) -> None:
        with patch.object(
            whiptail_tui,
            "_password_box",
            side_effect=["a", "b", "c", "d", "e", "f"],
        ), patch.object(whiptail_tui, "show_error"):
            with pytest.raises(TUIError, match="3 attempts"):
                whiptail_tui.show_passphrase_input()


# ---------------------------------------------------------------------------
# _get_whiptail_path
# ---------------------------------------------------------------------------


class TestGetWhiptailPath:
    def test_raises_when_not_installed(self) -> None:
        from installer.tui import _get_whiptail_path
        with patch("installer.tui.shutil.which", return_value=None):
            with pytest.raises(TUIError, match="whiptail not installed"):
                _get_whiptail_path()

    def test_returns_path_when_found(self) -> None:
        from installer.tui import _get_whiptail_path
        with patch("installer.tui.shutil.which", return_value="/usr/bin/whiptail"):
            assert _get_whiptail_path() == "/usr/bin/whiptail"


# ---------------------------------------------------------------------------
# Whiptail private helpers: _input_box, _password_box, _select_from_list
# ---------------------------------------------------------------------------


class TestWhiptailHelpers:
    def test_input_box_returns_value(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "typed value")):
            assert whiptail_tui._input_box("Title", "Prompt") == "typed value"

    def test_input_box_cancel_raises(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            with pytest.raises(TUIError, match="cancelled input"):
                whiptail_tui._input_box("Title", "Prompt")

    def test_password_box_returns_value(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "s3cr3t")):
            assert whiptail_tui._password_box("Title", "Prompt") == "s3cr3t"

    def test_password_box_cancel_raises(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            with pytest.raises(TUIError, match="cancelled password"):
                whiptail_tui._password_box("Title", "Prompt")


# ---------------------------------------------------------------------------
# Whiptail: show_hostname_input, show_partition_preview, show_summary
# ---------------------------------------------------------------------------


class TestWhiptailMiscScreens:
    def test_hostname_input_whiptail(self, whiptail_tui: TUI) -> None:
        with patch.object(whiptail_tui, "_input_box", return_value="my-host"):
            assert whiptail_tui.show_hostname_input() == "my-host"

    def test_partition_preview_calls_whiptail(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            whiptail_tui.show_partition_preview("/dev/sda", False)
        mock_wt.assert_called_once()
        assert "--msgbox" in mock_wt.call_args[0]

    def test_partition_preview_luks(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            whiptail_tui.show_partition_preview("/dev/sda", True)
        call_args = " ".join(str(a) for a in mock_wt.call_args[0])
        assert "LUKS" in call_args or "encrypted" in call_args

    def test_summary_whiptail(self, whiptail_tui: TUI) -> None:
        config = MagicMock()
        config.disk.device = "/dev/sda"
        config.disk.use_luks = False
        config.network.hostname = "test"
        config.user.username = "user"
        config.locale.locale = "en_US.UTF-8"
        config.locale.timezone = "UTC"
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            whiptail_tui.show_summary(config)
        mock_wt.assert_called_once()
        assert "--msgbox" in mock_wt.call_args[0]


# ---------------------------------------------------------------------------
# show_post_install_action
# ---------------------------------------------------------------------------


class TestShowPostInstallAction:
    def test_rich_reboot(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_select", return_value="reboot"):
            assert rich_tui.show_post_install_action() == "reboot"

    def test_rich_shutdown(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_select", return_value="shutdown"):
            assert rich_tui.show_post_install_action() == "shutdown"

    def test_whiptail_reboot(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert whiptail_tui.show_post_install_action() == "reboot"

    def test_whiptail_shutdown(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert whiptail_tui.show_post_install_action() == "shutdown"


# ---------------------------------------------------------------------------
# _rich_select
# ---------------------------------------------------------------------------


class TestRichSelect:
    def test_returns_selected_item(self, rich_tui: TUI) -> None:
        items = [("opt1", "Option 1"), ("opt2", "Option 2")]
        with _patch_rich() as mocks:
            mocks["IntPrompt"].ask.return_value = 1
            result = rich_tui._rich_select("Title", "Choose:", items, default="opt1")
        assert result == "opt1"

    def test_second_item(self, rich_tui: TUI) -> None:
        items = [("opt1", "Option 1"), ("opt2", "Option 2")]
        with _patch_rich() as mocks:
            mocks["IntPrompt"].ask.return_value = 2
            result = rich_tui._rich_select("Title", "Choose:", items)
        assert result == "opt2"

    def test_out_of_range_then_valid(self, rich_tui: TUI) -> None:
        items = [("opt1", "Option 1"), ("opt2", "Option 2")]
        with _patch_rich() as mocks:
            mocks["IntPrompt"].ask.side_effect = [99, 1]
            result = rich_tui._rich_select("Title", "Choose:", items)
        assert result == "opt1"


# ---------------------------------------------------------------------------
# show_wifi_connect dispatch
# ---------------------------------------------------------------------------


class TestShowWifiConnect:
    def test_rich_backend_calls_rich_method(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_wifi_connect", return_value=True) as mock:
            result = rich_tui.show_wifi_connect()
        assert result is True
        mock.assert_called_once()

    def test_whiptail_backend_calls_whiptail_method(self, whiptail_tui: TUI) -> None:
        with patch.object(whiptail_tui, "_whiptail_wifi_connect", return_value=False) as mock:
            result = whiptail_tui.show_wifi_connect()
        assert result is False
        mock.assert_called_once()


# ---------------------------------------------------------------------------
# _find_wifi_interface
# ---------------------------------------------------------------------------


class TestFindWifiInterface:
    def test_returns_none_when_iw_fails(self, rich_tui: TUI) -> None:
        fail = MagicMock()
        fail.returncode = 1
        fail.stdout = ""
        with patch("installer.tui.shutil.which", return_value=None), \
             patch("installer.tui.subprocess.run", return_value=fail), \
             patch("time.sleep"):
            assert rich_tui._find_wifi_interface() is None

    def test_returns_managed_interface(self, rich_tui: TUI) -> None:
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = (
            "phy#0\n"
            "\tInterface wlan0\n"
            "\t\ttype managed\n"
        )
        with patch("installer.tui.shutil.which", return_value=None), \
             patch("installer.tui.subprocess.run", return_value=ok):
            assert rich_tui._find_wifi_interface() == "wlan0"

    def test_returns_station_interface(self, rich_tui: TUI) -> None:
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = (
            "phy#0\n"
            "\tInterface wlan0\n"
            "\t\ttype station\n"
        )
        with patch("installer.tui.shutil.which", return_value=None), \
             patch("installer.tui.subprocess.run", return_value=ok):
            assert rich_tui._find_wifi_interface() == "wlan0"

    def test_returns_none_when_no_managed(self, rich_tui: TUI) -> None:
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = (
            "phy#0\n"
            "\tInterface wlan0\n"
            "\t\ttype AP\n"
        )
        with patch("installer.tui.shutil.which", return_value=None), \
             patch("installer.tui.subprocess.run", return_value=ok):
            assert rich_tui._find_wifi_interface() is None

    def test_rfkill_unblock_called_when_available(self, rich_tui: TUI) -> None:
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = (
            "phy#0\n"
            "\tInterface wlan0\n"
            "\t\ttype managed\n"
        )
        with patch("installer.tui.shutil.which", return_value="/usr/bin/rfkill"), \
             patch("installer.tui.subprocess.run", return_value=ok) as mock_run:
            result = rich_tui._find_wifi_interface()
        assert result == "wlan0"
        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args[0] == "/usr/bin/rfkill"
        assert "unblock" in first_call_args


# ---------------------------------------------------------------------------
# Rich passphrase: short passphrase retry
# ---------------------------------------------------------------------------


class TestRichPassphraseShortRetry:
    def test_short_passphrase_then_valid(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            # First attempt: passphrase "ab" matches confirm "ab" but too short
            # Second attempt: "secure123" matches "secure123" and is long enough
            mocks["Prompt"].ask.side_effect = ["ab", "ab", "secure123", "secure123"]
            result = rich_tui.show_passphrase_input()
        assert result == "secure123"


# ---------------------------------------------------------------------------
# Rich user creation: short password retry
# ---------------------------------------------------------------------------


class TestRichUserCreationShortPassword:
    def test_short_password_then_valid(self, rich_tui: TUI) -> None:
        with _patch_rich() as mocks:
            # username, then short/short, then valid/valid
            mocks["Prompt"].ask.side_effect = [
                "alice",
                "hi", "hi",
                "validpassword", "validpassword",
            ]
            result = rich_tui.show_user_creation()
        assert result["username"] == "alice"


# ---------------------------------------------------------------------------
# Remote config prompt tests
# ---------------------------------------------------------------------------

class TestRemoteConfigPrompt:
    """Tests for show_remote_config_prompt method."""

    def test_rich_returns_none_when_declined(self) -> None:
        """Rich backend returns None when user says no."""
        with _patch_rich() as mocks:
            tui = TUI(title="Test Installer")
            tui._console = mocks["Console"].return_value

            # Mock Confirm.ask to return False (user declines)
            mocks["Confirm"].ask.return_value = False

            result = tui.show_remote_config_prompt()
            assert result is None
            mocks["Confirm"].ask.assert_called_once_with(
                "  Use a remote configuration file?",
                default=False,
                console=tui._console,
            )

    def test_rich_returns_url_when_accepted(self) -> None:
        """Rich backend returns URL when user provides one."""
        with _patch_rich() as mocks:
            tui = TUI(title="Test Installer")
            tui._console = mocks["Console"].return_value

            # Mock sequence: Confirm.ask=True, Prompt.ask=URL
            mocks["Confirm"].ask.return_value = True
            mocks["Prompt"].ask.return_value = "https://example.com/config.yaml"

            result = tui.show_remote_config_prompt()
            assert result == "https://example.com/config.yaml"

            mocks["Confirm"].ask.assert_called_once()
            mocks["Prompt"].ask.assert_called_once_with(
                "  Enter config URL",
                console=tui._console,
            )

    def test_rich_empty_url_returns_none(self) -> None:
        """Rich backend returns None when user enters empty URL."""
        with _patch_rich() as mocks:
            tui = TUI(title="Test Installer")
            tui._console = mocks["Console"].return_value

            # Mock sequence: Confirm.ask=True, Prompt.ask=empty string
            mocks["Confirm"].ask.return_value = True
            mocks["Prompt"].ask.return_value = "   "  # Whitespace only

            result = tui.show_remote_config_prompt()
            assert result is None

    def test_whiptail_returns_none_on_cancel(self) -> None:
        """Whiptail backend returns None on cancel (non-zero return)."""
        with patch("installer.tui.HAS_RICH", False), \
             patch("installer.tui.shutil.which", return_value="/usr/bin/whiptail"), \
             patch("installer.tui._whiptail") as mock_whiptail:

            tui = TUI(title="Test Installer")

            # Mock first whiptail call to return non-zero (cancel)
            mock_whiptail.return_value = (1, "")

            result = tui.show_remote_config_prompt()
            assert result is None
            assert mock_whiptail.call_count == 1

    def test_whiptail_returns_url_on_success(self) -> None:
        """Whiptail backend returns URL on successful input."""
        with patch("installer.tui.HAS_RICH", False), \
             patch("installer.tui.shutil.which", return_value="/usr/bin/whiptail"), \
             patch("installer.tui._whiptail") as mock_whiptail:

            tui = TUI(title="Test Installer")

            # Mock first whiptail call: yes/no returns 0 (yes)
            mock_whiptail.return_value = (0, "")

            # Create side effect for the two calls
            def side_effect(*args):
                if "--yesno" in args:
                    return (0, "")  # Yes
                else:  # inputbox
                    return (0, "https://example.com/config.yaml")

            mock_whiptail.side_effect = side_effect

            result = tui.show_remote_config_prompt()
            assert result == "https://example.com/config.yaml"
            assert mock_whiptail.call_count == 2

    def test_whiptail_empty_url_returns_none(self) -> None:
        """Whiptail backend returns None when URL is empty/whitespace."""
        with patch("installer.tui.HAS_RICH", False), \
             patch("installer.tui.shutil.which", return_value="/usr/bin/whiptail"), \
             patch("installer.tui._whiptail") as mock_whiptail:

            tui = TUI(title="Test Installer")

            # Mock first whiptail call: yes/no returns 0 (yes)
            mock_whiptail.return_value = (0, "")

            # Mock second call: inputbox returns whitespace
            def side_effect(*args):
                if "--yesno" in args:
                    return (0, "")
                else:  # inputbox
                    return (0, "   ")  # Whitespace only

            mock_whiptail.side_effect = side_effect

            result = tui.show_remote_config_prompt()
            assert result is None


# ---------------------------------------------------------------------------
# Phase 3 — show_desktop_selection, show_dm_selection, show_shell_selection
# ---------------------------------------------------------------------------


class TestDesktopAndShellSelectionRich:
    """Cover the rich backend paths of the Phase 3 selection prompts."""

    def test_show_desktop_selection_rich_calls_rich_select(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_select", return_value="hyprland") as mock_select:
            result = rich_tui.show_desktop_selection()
        assert result == "hyprland"
        mock_select.assert_called_once()

    def test_show_dm_selection_rich_calls_rich_select(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_select", return_value="sddm") as mock_select:
            result = rich_tui.show_dm_selection(profile="hyprland")
        assert result == "sddm"
        mock_select.assert_called_once()

    def test_show_shell_selection_rich_calls_rich_select(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_select", return_value="fish") as mock_select:
            result = rich_tui.show_shell_selection()
        assert result == "fish"
        mock_select.assert_called_once()


class TestDesktopAndShellSelectionWhiptail:
    """Cover the whiptail backend paths of the Phase 3 selection prompts."""

    def test_show_desktop_selection_whiptail_calls_select_from_list(
        self, whiptail_tui: TUI
    ) -> None:
        with patch.object(whiptail_tui, "_select_from_list", return_value="gnome") as mock_sel:
            result = whiptail_tui.show_desktop_selection()
        assert result == "gnome"
        mock_sel.assert_called_once()

    def test_show_dm_selection_whiptail_calls_select_from_list(
        self, whiptail_tui: TUI
    ) -> None:
        with patch.object(whiptail_tui, "_select_from_list", return_value="gdm") as mock_sel:
            result = whiptail_tui.show_dm_selection(profile="gnome")
        assert result == "gdm"
        mock_sel.assert_called_once()

    def test_show_shell_selection_whiptail_calls_select_from_list(
        self, whiptail_tui: TUI
    ) -> None:
        with patch.object(whiptail_tui, "_select_from_list", return_value="zsh") as mock_sel:
            result = whiptail_tui.show_shell_selection()
        assert result == "zsh"
        mock_sel.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 3 — show_progress (whiptail path)
# ---------------------------------------------------------------------------


class TestShowProgressWhiptail:
    def test_whiptail_progress_calls_subprocess(self, whiptail_tui: TUI) -> None:
        """Covers the whiptail branch in show_progress (lines 227) and
        _whiptail_progress subprocess.run call (line 247)."""
        with patch("installer.tui.subprocess.run") as mock_run, \
             patch("installer.tui._get_whiptail_path", return_value="/usr/bin/whiptail"):
            whiptail_tui.show_progress("Installing", "Downloading...", 50)
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert "--gauge" in cmd
        assert "Installing" in cmd


# ---------------------------------------------------------------------------
# Phase 3 — _scan_wifi_networks (subprocess mock)
# ---------------------------------------------------------------------------


class TestScanWifiNetworks:
    def test_scan_returns_empty_on_failure(self, rich_tui: TUI) -> None:
        """Covers _scan_wifi_networks lines 793-814 (failure path)."""
        with patch("installer.tui.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = rich_tui._scan_wifi_networks("wlan0")
        assert result == []

    def test_scan_parses_network_list(self, rich_tui: TUI) -> None:
        """Covers _scan_wifi_networks success path with parsed output."""
        # iwctl output: 4+ space-separated fields per network line (SSID sec signal extra)
        fake_output = (
            "Available networks\n"
            "---\n"
            "SSID            Security    Signal      Extra\n"
            "---\n"
            "HomeNet         psk         **          x\n"
            "OpenNet         open        *           x\n"
        )

        def side_effect(cmd: list[str], **kwargs):
            if "scan" in cmd:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout=fake_output)

        with patch("installer.tui.subprocess.run", side_effect=side_effect), \
             patch("time.sleep"):
            result = rich_tui._scan_wifi_networks("wlan0")

        # Returns a list of (ssid, security, is_open) tuples
        assert isinstance(result, list)
        assert any(ssid == "HomeNet" for ssid, _, _ in result)

    def test_find_wifi_interface_returns_none_when_no_station(self, rich_tui: TUI) -> None:
        """Covers _find_wifi_interface when no managed/station type is found."""
        with patch("installer.tui.shutil.which", return_value=None), \
             patch("installer.tui.subprocess.run") as mock_run, \
             patch("time.sleep"):
            mock_run.return_value = MagicMock(returncode=0, stdout="phy#0\n  Interface wlan0\n")
            result = rich_tui._find_wifi_interface()
        assert result is None


# ---------------------------------------------------------------------------
# Secure Boot prompt
# ---------------------------------------------------------------------------


class TestSecureBootPrompt:
    def test_rich_dispatches_to_rich_impl(self, rich_tui: TUI) -> None:
        with patch.object(rich_tui, "_rich_secure_boot_prompt") as mock_impl:
            rich_tui.show_secure_boot_prompt()
        mock_impl.assert_called_once()

    def test_whiptail_dispatches_to_whiptail_impl(self, whiptail_tui: TUI) -> None:
        with patch.object(whiptail_tui, "_whiptail_secure_boot_prompt") as mock_impl:
            whiptail_tui.show_secure_boot_prompt()
        mock_impl.assert_called_once()

    def test_rich_secure_boot_prompt_shows_panel_and_confirm(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            tui._rich_secure_boot_prompt()
        mocks["Console"].return_value.print.assert_called_once()
        mocks["Confirm"].ask.assert_called_once()

    def test_whiptail_secure_boot_prompt_calls_msgbox(self, whiptail_tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_w:
            whiptail_tui._whiptail_secure_boot_prompt()
        args = mock_w.call_args[0]
        assert "--msgbox" in args
        assert "Setup Mode" in " ".join(str(a) for a in args)


# ---------------------------------------------------------------------------
# Rich WiFi connect
# ---------------------------------------------------------------------------


class TestRichWifiConnect:
    def test_returns_false_when_no_wifi_interface(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            with patch.object(tui, "_find_wifi_interface", return_value=None):
                result = tui._rich_wifi_connect()
        assert result is False

    def test_returns_false_when_no_networks(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            with patch.object(tui, "_find_wifi_interface", return_value="wlan0"), \
                 patch.object(tui, "_scan_wifi_networks", return_value=[]):
                result = tui._rich_wifi_connect()
        assert result is False

    def test_returns_false_when_user_skips(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            networks = [("HomeNet", "WPA2", False)]
            mocks["IntPrompt"].ask.return_value = 0
            with patch.object(tui, "_find_wifi_interface", return_value="wlan0"), \
                 patch.object(tui, "_scan_wifi_networks", return_value=networks):
                result = tui._rich_wifi_connect()
        assert result is False

    def test_open_network_success(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            networks = [("CafeWifi", "open", True)]
            mocks["IntPrompt"].ask.return_value = 1
            ok = MagicMock(returncode=0)
            ping_ok = MagicMock(returncode=0)
            with patch.object(tui, "_find_wifi_interface", return_value="wlan0"), \
                 patch.object(tui, "_scan_wifi_networks", return_value=networks), \
                 patch("installer.tui.subprocess.run", side_effect=[ok, ping_ok]), \
                 patch("time.sleep"):
                result = tui._rich_wifi_connect()
        assert result is True

    def test_wpa_network_connection_failure(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            networks = [("HomeNet", "WPA2", False)]
            mocks["IntPrompt"].ask.return_value = 1
            mocks["Prompt"].ask.return_value = "badpassword"
            fail = MagicMock(returncode=1, stderr="Authentication failed")
            with patch.object(tui, "_find_wifi_interface", return_value="wlan0"), \
                 patch.object(tui, "_scan_wifi_networks", return_value=networks), \
                 patch("installer.tui.subprocess.run", return_value=fail):
                result = tui._rich_wifi_connect()
        assert result is False

    def test_connected_but_no_internet(self) -> None:
        with _patch_rich() as mocks:
            tui = TUI(title="Test")
            tui._console = mocks["Console"].return_value
            networks = [("HomeNet", "WPA2", False)]
            mocks["IntPrompt"].ask.return_value = 1
            mocks["Prompt"].ask.return_value = "password"
            ok = MagicMock(returncode=0)
            ping_fail = MagicMock(returncode=1)
            with patch.object(tui, "_find_wifi_interface", return_value="wlan0"), \
                 patch.object(tui, "_scan_wifi_networks", return_value=networks), \
                 patch("installer.tui.subprocess.run", side_effect=[ok, ping_fail]), \
                 patch("time.sleep"):
                result = tui._rich_wifi_connect()
        assert result is False


# ---------------------------------------------------------------------------
# Whiptail WiFi connect
# ---------------------------------------------------------------------------


class TestWhiptailWifiConnect:
    def test_returns_false_when_no_interface(self, whiptail_tui: TUI) -> None:
        with patch.object(whiptail_tui, "_find_wifi_interface", return_value=None), \
             patch.object(whiptail_tui, "show_error"):
            result = whiptail_tui._whiptail_wifi_connect()
        assert result is False

    def test_returns_false_when_no_networks(self, whiptail_tui: TUI) -> None:
        with patch.object(whiptail_tui, "_find_wifi_interface", return_value="wlan0"), \
             patch.object(whiptail_tui, "_scan_wifi_networks", return_value=[]), \
             patch.object(whiptail_tui, "show_error"):
            result = whiptail_tui._whiptail_wifi_connect()
        assert result is False

    def test_returns_false_when_user_skips(self, whiptail_tui: TUI) -> None:
        networks = [("HomeNet", "WPA2", False)]
        with patch.object(whiptail_tui, "_find_wifi_interface", return_value="wlan0"), \
             patch.object(whiptail_tui, "_scan_wifi_networks", return_value=networks), \
             patch.object(whiptail_tui, "_select_from_list", return_value="skip"):
            result = whiptail_tui._whiptail_wifi_connect()
        assert result is False

    def test_open_network_ping_success(self, whiptail_tui: TUI) -> None:
        networks = [("CafeWifi", "open", True)]
        ok = MagicMock(returncode=0)
        ping_ok = MagicMock(returncode=0)
        with patch.object(whiptail_tui, "_find_wifi_interface", return_value="wlan0"), \
             patch.object(whiptail_tui, "_scan_wifi_networks", return_value=networks), \
             patch.object(whiptail_tui, "_select_from_list", return_value="CafeWifi"), \
             patch("installer.tui.subprocess.run", side_effect=[ok, ping_ok]), \
             patch("time.sleep"):
            result = whiptail_tui._whiptail_wifi_connect()
        assert result is True

    def test_wpa_connection_failure(self, whiptail_tui: TUI) -> None:
        networks = [("HomeNet", "WPA2", False)]
        fail = MagicMock(returncode=1, stderr="auth failed")
        with patch.object(whiptail_tui, "_find_wifi_interface", return_value="wlan0"), \
             patch.object(whiptail_tui, "_scan_wifi_networks", return_value=networks), \
             patch.object(whiptail_tui, "_select_from_list", return_value="HomeNet"), \
             patch.object(whiptail_tui, "_password_box", return_value="wrong"), \
             patch.object(whiptail_tui, "show_error"), \
             patch("installer.tui.subprocess.run", return_value=fail):
            result = whiptail_tui._whiptail_wifi_connect()
        assert result is False
