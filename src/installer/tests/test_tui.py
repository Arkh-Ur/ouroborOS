"""test_tui.py — Tests for the TUI module.

TUI tests mock whiptail and subprocess to avoid requiring a terminal.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from installer.tui import TUI, TUIError, _hash_password, _lsblk_disks, _whiptail

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tui() -> TUI:
    """Return a TUI instance with whiptail check bypassed."""
    with patch("installer.tui.TUI._check_whiptail"):
        return TUI(title="Test Installer")


# ---------------------------------------------------------------------------
# _whiptail wrapper
# ---------------------------------------------------------------------------


class TestWhiptailWrapper:
    def test_returns_returncode_and_stderr(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = "selected_item"
        wp = patch(
            "installer.tui._get_whiptail_path",
            return_value="/usr/bin/whiptail",
        )
        sr = patch(
            "installer.tui.subprocess.run",
            return_value=mock_result,
        )
        with wp, sr:
            rc, output = _whiptail("--msgbox", "hello", "10", "40")
        assert rc == 0
        assert output == "selected_item"

    def test_cancel_returns_nonzero_rc(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        wp = patch(
            "installer.tui._get_whiptail_path",
            return_value="/usr/bin/whiptail",
        )
        sr = patch(
            "installer.tui.subprocess.run",
            return_value=mock_result,
        )
        with wp, sr:
            rc, _ = _whiptail("--msgbox", "bye", "10", "40")
        assert rc == 1


# ---------------------------------------------------------------------------
# _lsblk_disks
# ---------------------------------------------------------------------------


class TestLsblkDisks:
    def test_parses_lsblk_json(self) -> None:
        lsblk_output = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "sda", "size": "500G", "model": "Samsung SSD",
                        "type": "disk", "hotplug": False,
                    },
                    {
                        "name": "sda1", "size": "512M", "model": None,
                        "type": "part", "hotplug": False,
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
# _hash_password
# ---------------------------------------------------------------------------


class TestHashPassword:
    def test_hash_starts_with_sha512_marker(self) -> None:
        hashed = _hash_password("mypassword")
        assert hashed.startswith("$6$")

    def test_same_password_different_salt(self) -> None:
        h1 = _hash_password("password")
        h2 = _hash_password("password")
        # Different salts → different hashes
        assert h1 != h2

    def test_hash_is_verifiable(self) -> None:
        import subprocess
        password = "testpass123"
        hashed = _hash_password(password)
        # Extract salt from $6$<salt>$<hash> and re-hash to verify
        salt = hashed.split("$")[2]
        result = subprocess.run(
            ["openssl", "passwd", "-6", "-salt", salt, password],
            capture_output=True, text=True, check=True,
        )
        assert result.stdout.strip() == hashed


# ---------------------------------------------------------------------------
# TUI screens
# ---------------------------------------------------------------------------


class TestTUICheckWhiptail:
    def test_raises_when_whiptail_missing(self) -> None:
        with patch("installer.tui.shutil.which", return_value=None):
            with pytest.raises(TUIError, match="whiptail"):
                TUI()


class TestTUIShowWelcome:
    def test_show_welcome_calls_whiptail(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail") as mock_wt:
            mock_wt.return_value = (0, "")
            tui.show_welcome()
        mock_wt.assert_called_once()
        call_args = mock_wt.call_args[0]
        assert "--msgbox" in call_args


class TestTUIShowError:
    def test_recoverable_error_yes_returns_true(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            result = tui.show_error("Something broke", recoverable=True)
        assert result is True
        call_args = mock_wt.call_args[0]
        assert "--yesno" in call_args

    def test_recoverable_error_no_returns_false(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            result = tui.show_error("Something broke", recoverable=True)
        assert result is False

    def test_fatal_error_always_returns_false(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            result = tui.show_error("Fatal!", recoverable=False)
        assert result is False

    def test_fatal_error_uses_msgbox(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")) as mock_wt:
            tui.show_error("Fatal!", recoverable=False)
        call_args = mock_wt.call_args[0]
        assert "--msgbox" in call_args


class TestTUIShowConfirmation:
    def test_yes_returns_true(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert tui.show_confirmation("Are you sure?") is True

    def test_no_returns_false(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert tui.show_confirmation("Are you sure?") is False


class TestTUIShowDiskSelection:
    def test_returns_selected_disk(self, tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "500G", "model": "SAMSUNG"}]
        with patch("installer.tui._lsblk_disks", return_value=disks), \
             patch("installer.tui._whiptail", return_value=(0, "/dev/sda")):
            result = tui.show_disk_selection()
        assert result == "/dev/sda"

    def test_raises_when_no_disks(self, tui: TUI) -> None:
        with patch("installer.tui._lsblk_disks", return_value=[]):
            with pytest.raises(TUIError, match="No suitable"):
                tui.show_disk_selection()

    def test_raises_on_cancel(self, tui: TUI) -> None:
        disks = [{"name": "/dev/sda", "size": "100G", "model": "Disk"}]
        with patch("installer.tui._lsblk_disks", return_value=disks), \
             patch("installer.tui._whiptail", return_value=(1, "")):
            with pytest.raises(TUIError):
                tui.show_disk_selection()


class TestTUIShowLocaleMenu:
    def test_returns_locale_dict(self, tui: TUI) -> None:
        with (
            patch.object(tui, "_select_from_list", side_effect=["en_US.UTF-8", "us"]),
            patch.object(tui, "_input_box", return_value="America/New_York"),
        ):
            result = tui.show_locale_menu()
        assert result["locale"] == "en_US.UTF-8"
        assert result["keymap"] == "us"
        assert result["timezone"] == "America/New_York"


class TestTUIShowUserCreation:
    def test_successful_user_creation(self, tui: TUI) -> None:
        with (
            patch.object(tui, "_input_box", return_value="alice"),
            patch.object(
                tui, "_password_box", side_effect=["password123", "password123"]
            ),
        ):
            result = tui.show_user_creation()
        assert result["username"] == "alice"
        assert result["password_hash"].startswith("$6$")

    def test_password_mismatch_retries(self, tui: TUI) -> None:
        with patch.object(tui, "_input_box", return_value="bob"), \
             patch.object(
                 tui,
                 "_password_box",
                 side_effect=["pass1", "pass2", "pass1", "pass2", "pass1", "pass2"],
             ), \
             patch.object(tui, "show_error"):
            with pytest.raises(TUIError, match="3 attempts"):
                tui.show_user_creation()

    def test_short_password_retries(self, tui: TUI) -> None:
        with patch.object(tui, "_input_box", return_value="carol"), \
             patch.object(
                 tui,
                 "_password_box",
                 side_effect=["hi", "hi", "validpassword", "validpassword"],
             ), \
             patch.object(tui, "show_error"):
            result = tui.show_user_creation()
        assert result["username"] == "carol"


class TestTUIShowLuks:
    def test_luks_yes_returns_true(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(0, "")):
            assert tui.show_luks_prompt() is True

    def test_luks_no_returns_false(self, tui: TUI) -> None:
        with patch("installer.tui._whiptail", return_value=(1, "")):
            assert tui.show_luks_prompt() is False


class TestTUIPassphraseInput:
    def test_matching_passphrases_returned(self, tui: TUI) -> None:
        with patch.object(tui, "_password_box", side_effect=["secure123", "secure123"]):
            result = tui.show_passphrase_input()
        assert result == "secure123"

    def test_mismatch_then_match(self, tui: TUI) -> None:
        with patch.object(
            tui, "_password_box",
            side_effect=["wrong", "right", "correct!!", "correct!!"],
        ), patch.object(tui, "show_error"):
            result = tui.show_passphrase_input()
        assert result == "correct!!"

    def test_short_passphrase_retries(self, tui: TUI) -> None:
        with patch.object(
            tui, "_password_box",
            side_effect=["short", "short", "longpassword", "longpassword"],
        ), patch.object(tui, "show_error"):
            result = tui.show_passphrase_input()
        assert result == "longpassword"

    def test_too_many_mismatches_raises(self, tui: TUI) -> None:
        with patch.object(
            tui, "_password_box",
            side_effect=["a", "b", "c", "d", "e", "f"],
        ), patch.object(tui, "show_error"):
            with pytest.raises(TUIError, match="3 attempts"):
                tui.show_passphrase_input()
