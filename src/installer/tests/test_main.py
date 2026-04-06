"""test_main.py — Tests for the installer CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from installer.main import _build_parser, cmd_validate_config, main


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_returns_parser(self) -> None:
        parser = _build_parser()
        assert parser is not None
        assert parser.prog == "ouroborOS-installer"

    def test_default_target_is_mnt(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.target == "/mnt"

    def test_resume_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--resume"])
        assert args.resume is True

    def test_config_flag(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("disk:\n  device: /dev/vda\n")
        parser = _build_parser()
        args = parser.parse_args(["--config", str(config_file)])
        assert args.config == config_file

    def test_validate_config_flag(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        parser = _build_parser()
        args = parser.parse_args(["--validate-config", str(config_file)])
        assert args.validate_config == config_file

    def test_custom_target(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--target", "/mnt/custom"])
        assert args.target == "/mnt/custom"


# ---------------------------------------------------------------------------
# cmd_validate_config
# ---------------------------------------------------------------------------


class TestCmdValidateConfig:
    def test_file_not_found_returns_one(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.yaml"
        result = cmd_validate_config(missing)
        assert result == 1

    def test_valid_config_returns_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        config_file = tmp_path / "config.yaml"
        # Minimal valid config
        config_file.write_text(
            "disk:\n  device: /dev/vda\n"
            "user:\n  username: testuser\n"
            "network:\n  hostname: testhost\n"
        )
        with patch("installer.main.validate_config") as mock_validate:
            mock_validate.return_value = None
            result = cmd_validate_config(config_file)
        assert result == 0
        captured = capsys.readouterr()
        assert "Config valid" in captured.out

    def test_invalid_config_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("disk:\n  device: /dev/vda\n")
        with patch("installer.main.validate_config", side_effect=Exception("bad config")):
            result = cmd_validate_config(config_file)
        assert result == 1
        captured = capsys.readouterr()
        assert "Config invalid" in captured.err

    def test_invalid_yaml_returns_one(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: [unclosed")
        result = cmd_validate_config(config_file)
        assert result == 1


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_validate_config_mode(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("disk:\n  device: /dev/vda\n")
        with patch("sys.argv", ["ouroborOS-installer", "--validate-config", str(config_file)]), \
             patch("installer.main.cmd_validate_config", return_value=0) as mock_validate:
            result = main()
        assert result == 0
        mock_validate.assert_called_once_with(config_file)

    def test_install_mode_returns_installer_exit_code(self) -> None:
        mock_installer = MagicMock()
        mock_installer.run.return_value = 0
        with patch("sys.argv", ["ouroborOS-installer"]), \
             patch("installer.main.Installer", return_value=mock_installer):
            result = main()
        assert result == 0
        mock_installer.run.assert_called_once()

    def test_resume_flag_passed_to_installer(self) -> None:
        mock_installer = MagicMock()
        mock_installer.run.return_value = 0
        with patch("sys.argv", ["ouroborOS-installer", "--resume"]), \
             patch("installer.main.Installer", return_value=mock_installer) as mock_cls:
            main()
        mock_cls.assert_called_once_with(resume=True, config_path=None)

    def test_config_flag_passed_to_installer(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        mock_installer = MagicMock()
        mock_installer.run.return_value = 0
        with patch("sys.argv", ["ouroborOS-installer", "--config", str(config_file)]), \
             patch("installer.main.Installer", return_value=mock_installer) as mock_cls:
            main()
        mock_cls.assert_called_once_with(resume=False, config_path=config_file)

    def test_custom_target_sets_install_target(self) -> None:
        mock_installer = MagicMock()
        mock_installer.run.return_value = 0
        mock_installer.config = MagicMock()
        with patch("sys.argv", ["ouroborOS-installer", "--target", "/mnt/test"]), \
             patch("installer.main.Installer", return_value=mock_installer):
            main()
        assert mock_installer.config.install_target == "/mnt/test"

    def test_install_failure_returns_one(self) -> None:
        mock_installer = MagicMock()
        mock_installer.run.return_value = 1
        with patch("sys.argv", ["ouroborOS-installer"]), \
             patch("installer.main.Installer", return_value=mock_installer):
            result = main()
        assert result == 1
