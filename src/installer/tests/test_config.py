"""test_config.py — Tests for the installer configuration module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from installer.config import (
    ConfigValidationError,
    InstallerConfig,
    load_config,
    validate_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return its path."""
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


VALID_CONFIG = """\
    disk:
      device: /dev/sda
      use_luks: false
      btrfs_label: ouroborOS
      swap_type: zram

    locale:
      locale: en_US.UTF-8
      keymap: us
      timezone: UTC

    network:
      hostname: ouroboros

    user:
      username: testuser
      password_hash: "$6$salt$hash"
      groups:
        - wheel
        - audio
"""


# ---------------------------------------------------------------------------
# validate_config — happy path
# ---------------------------------------------------------------------------


class TestValidateConfigHappyPath:
    def test_valid_config_passes(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        validate_config(data)  # Should not raise

    def test_valid_nvme_device(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["disk"]["device"] = "/dev/nvme0n1"
        validate_config(data)

    def test_minimal_config(self) -> None:
        minimal = {
            "disk": {"device": "/dev/vda"},
            "locale": {"timezone": "Europe/Madrid"},
            "network": {"hostname": "myhost"},
            "user": {"username": "alice", "password_hash": "$6$x$y"},
        }
        validate_config(minimal)

    def test_timezone_with_sub_region(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["locale"]["timezone"] = "America/New_York"
        validate_config(data)

    def test_hostname_with_hyphens(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["hostname"] = "my-awesome-host"
        validate_config(data)


# ---------------------------------------------------------------------------
# validate_config — error cases
# ---------------------------------------------------------------------------


class TestValidateConfigErrors:
    def test_missing_disk_section(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["disk"]
        with pytest.raises(ConfigValidationError, match="disk"):
            validate_config(data)

    def test_missing_locale_section(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["locale"]
        with pytest.raises(ConfigValidationError, match="locale"):
            validate_config(data)

    def test_missing_network_section(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["network"]
        with pytest.raises(ConfigValidationError, match="network"):
            validate_config(data)

    def test_missing_user_section(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["user"]
        with pytest.raises(ConfigValidationError, match="user"):
            validate_config(data)

    def test_device_not_absolute(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["disk"]["device"] = "sda"
        with pytest.raises(ConfigValidationError, match="disk.device"):
            validate_config(data)

    def test_device_is_partition_not_disk(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["disk"]["device"] = "/dev/sda1"
        with pytest.raises(ConfigValidationError, match="partition"):
            validate_config(data)

    def test_invalid_timezone(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["locale"]["timezone"] = "Not/A/Valid-Zone!"
        with pytest.raises(ConfigValidationError, match="timezone"):
            validate_config(data)

    def test_invalid_hostname_starts_with_hyphen(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["hostname"] = "-badhost"
        with pytest.raises(ConfigValidationError, match="hostname"):
            validate_config(data)

    def test_invalid_username_uppercase(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["username"] = "MyUser"
        with pytest.raises(ConfigValidationError, match="username"):
            validate_config(data)

    def test_invalid_username_starts_with_digit(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["username"] = "1user"
        with pytest.raises(ConfigValidationError, match="username"):
            validate_config(data)

    def test_missing_password_field(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["user"]["password_hash"]
        with pytest.raises(ConfigValidationError, match="password"):
            validate_config(data)

    def test_plaintext_password_accepted(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["user"]["password_hash"]
        data["user"]["password"] = "mypassword"
        validate_config(data)  # Should not raise (plaintext is accepted at parse time)

    def test_missing_disk_device(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["disk"]["device"]
        with pytest.raises(ConfigValidationError, match="device"):
            validate_config(data)

    def test_missing_timezone(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["locale"]["timezone"]
        with pytest.raises(ConfigValidationError, match="timezone"):
            validate_config(data)

    def test_missing_hostname(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["network"]["hostname"]
        with pytest.raises(ConfigValidationError, match="hostname"):
            validate_config(data)

    def test_missing_username(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        del data["user"]["username"]
        with pytest.raises(ConfigValidationError, match="username"):
            validate_config(data)


# ---------------------------------------------------------------------------
# load_config — file-based tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_valid_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_CONFIG)
        cfg = load_config(path)

        assert isinstance(cfg, InstallerConfig)
        assert cfg.disk.device == "/dev/sda"
        assert cfg.disk.use_luks is False
        assert cfg.disk.btrfs_label == "ouroborOS"
        assert cfg.locale.locale == "en_US.UTF-8"
        assert cfg.locale.keymap == "us"
        assert cfg.locale.timezone == "UTC"
        assert cfg.network.hostname == "ouroboros"
        assert cfg.user.username == "testuser"
        assert cfg.unattended is True

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("{ invalid: yaml: content: ::::", encoding="utf-8")
        with pytest.raises(Exception):
            load_config(p)

    def test_non_mapping_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigValidationError, match="mapping"):
            load_config(p)

    def test_luks_enabled_sets_flag(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("use_luks: false", "use_luks: true")
        path = _write_yaml(tmp_path, content)
        cfg = load_config(path)
        assert cfg.disk.use_luks is True
        assert cfg.enable_luks is True

    def test_extra_packages_loaded(self, tmp_path: Path) -> None:
        # Dedent VALID_CONFIG first so appended lines align at column 0
        import textwrap as _tw
        base = _tw.dedent(VALID_CONFIG)
        content = base + "\nextra_packages:\n  - neovim\n  - tmux\n"
        p = tmp_path / "config.yaml"
        p.write_text(content, encoding="utf-8")
        cfg = load_config(p)
        assert "neovim" in cfg.extra_packages
        assert "tmux" in cfg.extra_packages

    def test_defaults_applied(self, tmp_path: Path) -> None:
        minimal = """\
            disk:
              device: /dev/vda
            locale:
              timezone: UTC
            network:
              hostname: myhost
            user:
              username: alice
              password_hash: "$6$x$y"
        """
        path = _write_yaml(tmp_path, minimal)
        cfg = load_config(path)
        assert cfg.locale.locale == "en_US.UTF-8"
        assert cfg.locale.keymap == "us"
        assert cfg.disk.btrfs_label == "ouroborOS"
        assert cfg.network.enable_networkd is True
