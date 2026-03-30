"""test_tui.py — Tests for the TUI module.

Tests both rich and whiptail backends using mocks.
Utility functions (_lsblk_disks, _hash_password) are backend-independent.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from installer.tui import (
    TUI,
    TUIError,
    _hash_password,
    _lsblk_disks,
    _whiptail,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rich_tui() -> TUI:
    mock_console = MagicMock()
    with patch("installer.tui.HAS_RICH", True), patch(
        "installer.tui.Console", return_value=mock_console
    ):
        tui = TUI(title="Test Installer")
        tui._console = mock_console
        return tui


@pytest.fixture()
def whiptail_tui() -> TUI:
    with patch("installer.tui.HAS_RICH", False), patch(
        "installer.tui.shutil.which", return_value="/usr/bin/whiptail"
    ):
        return TUI(title="Test Installer")


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


class TestBackendSelection:
    def test_rich_backend_when_available(self) -> None:
        mock_console = MagicMock()
        with patch("installer.tui.HAS_RICH", True), patch(
            "installer.tui.Console", return_value=mock_console
        ):
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
        with patch("installer.tui.Prompt"):
            rich_tui.show_welcome()
        rich_tui._console.print.assert_called()


class TestRichShowProgress:
    def test_creates_progress(self, rich_tui: TUI) -> None:
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 1
        with patch("installer.tui.Progress", return_value=mock_progress):
            rich_tui.show_progress("Test", "Working...", 50)
        mock_progress.start.assert_called_once()
        mock_progress.add_task.assert_called_once()

    def test_stops_at_100(self, rich_tui: TUI) -> None:
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 1
        with patch("installer.tui.Progress", return_value=mock_progress):
            rich_tui.show_progress("Test", "Done!", 100)
        mock_progress.stop.assert_called()

    def test_updates_existing_progress(self, rich_tui: TUI) -> None:
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 1
        with patch("installer.tui.Progress", return_value=mock_progress):
            rich_tui.show_progress("Test", "Working...", 50)
            rich_tui.show_progress("Test", "Still working...", 75)
        mock_progress.update.assert_called()


class TestRichShowError:
    def test_recoverable_yes_returns_true(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = True
            assert rich_tui.show_error("Oops", recoverable=True) is True

    def test_recoverable_no_returns_false(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = False
            assert rich_tui.show_error("Oops", recoverable=True) is False

    def test_fatal_returns_false(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm"):
            assert rich_tui.show_error("Fatal!", recoverable=False) is False


class TestRichShowConfirmation:
    def test_yes_returns_true(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = True
            assert rich_tui.show_confirmation("Sure?") is True

    def test_no_returns_false(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = False
            assert rich_tui.show_confirmation("Sure?") is False


class TestRichShowLuksPrompt:
    def test_yes_returns_true(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = True
            assert rich_tui.show_luks_prompt() is True

    def test_no_returns_false(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Confirm") as mock:
            mock.ask.return_value = False
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
        with patch("installer.tui.Prompt") as mock:
            mock.ask.return_value = "myhost"
            assert rich_tui.show_hostname_input() == "myhost"


class TestRichShowDiskSelection:
    def test_returns_selected_disk(self, rich_tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "500G", "model": "SAMSUNG"}]
        with patch(
            "installer.tui._lsblk_disks", return_value=disks
        ), patch.object(rich_tui, "_rich_select", return_value="/dev/sda"):
            assert rich_tui.show_disk_selection() == "/dev/sda"

    def test_raises_when_no_disks(self, rich_tui: TUI) -> None:
        with patch("installer.tui._lsblk_disks", return_value=[]):
            with pytest.raises(TUIError, match="No suitable"):
                rich_tui.show_disk_selection()


class TestRichShowUserCreation:
    def test_successful_creation(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = [
                "alice",
                "password123",
                "password123",
            ]
            result = rich_tui.show_user_creation()
        assert result["username"] == "alice"
        assert result["password_hash"].startswith("$6$")

    def test_password_mismatch_raises(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = [
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
        with patch("installer.tui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["secure123", "secure123"]
            assert rich_tui.show_passphrase_input() == "secure123"

    def test_too_many_mismatches(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["a", "b", "c", "d", "e", "f"]
            with pytest.raises(TUIError, match="3 attempts"):
                rich_tui.show_passphrase_input()


class TestRichShowPartitionPreview:
    def test_prints_tables(self, rich_tui: TUI) -> None:
        with patch("installer.tui.Prompt"):
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
        with patch("installer.tui.Prompt"):
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
            patch.object(
                whiptail_tui, "_input_box", return_value="alice"
            ),
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
            side_effect=["short", "short", "longpassword", "longpassword"],
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
