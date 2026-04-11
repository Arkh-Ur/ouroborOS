"""test_config.py — Tests for the installer configuration module."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from installer.config import (
    ConfigValidationError,
    InstallerConfig,
    SecurityConfig,
    find_unattended_config,
    load_config,
    load_config_from_url,
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


# ---------------------------------------------------------------------------
# Phase 3 — WiFi pre-configuration tests (3.9.3)
# ---------------------------------------------------------------------------


class TestWifiConfig:
    def test_wifi_ssid_and_passphrase_accepted(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["wifi"] = {"ssid": "MyNet", "passphrase": "secret"}
        validate_config(data)  # must not raise

    def test_wifi_ssid_without_passphrase_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["wifi"] = {"ssid": "MyNet"}
        with pytest.raises(ConfigValidationError, match="passphrase"):
            validate_config(data)

    def test_wifi_passphrase_without_ssid_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["wifi"] = {"passphrase": "secret"}
        with pytest.raises(ConfigValidationError, match="ssid"):
            validate_config(data)

    def test_wifi_empty_section_accepted(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["network"]["wifi"] = {}
        validate_config(data)  # empty wifi block is fine

    def test_wifi_loaded_into_config(self, tmp_path: Path) -> None:
        base = textwrap.dedent(VALID_CONFIG)
        content = base + "\n"
        # Inject wifi subsection into network block
        content = content.replace(
            "network:\n  hostname: ouroboros\n",
            "network:\n  hostname: ouroboros\n  wifi:\n    ssid: TestNet\n    passphrase: letmein\n",
        )
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.network.wifi_ssid == "TestNet"
        assert cfg.network.wifi_passphrase == "letmein"

    def test_wifi_absent_defaults_to_empty(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_CONFIG)
        cfg = load_config(path)
        assert cfg.network.wifi_ssid == ""
        assert cfg.network.wifi_passphrase == ""

    def test_bluetooth_enable_loaded(self, tmp_path: Path) -> None:
        base = textwrap.dedent(VALID_CONFIG)
        content = base.replace(
            "network:\n  hostname: ouroboros\n",
            "network:\n  hostname: ouroboros\n  bluetooth:\n    enable: true\n",
        )
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.network.bluetooth_enable is True

    def test_bluetooth_enable_default_false(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_CONFIG)
        cfg = load_config(path)
        assert cfg.network.bluetooth_enable is False


# ---------------------------------------------------------------------------
# Phase 3 — SecurityConfig tests (3.9.4)
# ---------------------------------------------------------------------------


class TestSecurityConfig:
    def test_security_defaults(self) -> None:
        sec = SecurityConfig()
        assert sec.secure_boot is False
        assert sec.sbctl_include_ms_keys is False

    def test_security_section_optional(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        assert "security" not in data
        validate_config(data)  # must not raise

    def test_security_secure_boot_true_accepted(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["security"] = {"secure_boot": True}
        validate_config(data)  # must not raise

    def test_security_secure_boot_non_bool_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["security"] = {"secure_boot": "yes"}
        with pytest.raises(ConfigValidationError, match="boolean"):
            validate_config(data)

    def test_security_loaded_into_config(self, tmp_path: Path) -> None:
        base = textwrap.dedent(VALID_CONFIG)
        content = base + "\nsecurity:\n  secure_boot: true\n  sbctl_include_ms_keys: true\n"
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.security.secure_boot is True
        assert cfg.security.sbctl_include_ms_keys is True

    def test_security_absent_defaults(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, VALID_CONFIG)
        cfg = load_config(path)
        assert cfg.security.secure_boot is False
        assert cfg.security.sbctl_include_ms_keys is False


# ---------------------------------------------------------------------------
# Phase 3 — Additional validate_config branches
# ---------------------------------------------------------------------------


class TestValidateConfigBranches:
    def test_invalid_homed_storage_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["homed_storage"] = "btrfs"
        with pytest.raises(ConfigValidationError, match="homed_storage"):
            validate_config(data)

    def test_valid_homed_storage_classic(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["homed_storage"] = "classic"
        validate_config(data)  # must not raise

    def test_valid_homed_storage_luks(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["homed_storage"] = "luks"
        validate_config(data)  # must not raise

    def test_invalid_shell_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["shell"] = "/bin/tcsh"
        with pytest.raises(ConfigValidationError, match="shell"):
            validate_config(data)

    def test_valid_shell_zsh(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["shell"] = "/bin/zsh"
        validate_config(data)

    def test_valid_shell_fish(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["user"]["shell"] = "/usr/bin/fish"
        validate_config(data)

    def test_invalid_desktop_profile_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["desktop"] = {"profile": "lxqt"}
        with pytest.raises(ConfigValidationError, match="desktop.profile"):
            validate_config(data)

    def test_valid_desktop_profile_hyprland(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["desktop"] = {"profile": "hyprland"}
        validate_config(data)

    def test_invalid_desktop_dm_raises(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["desktop"] = {"profile": "minimal", "dm": "lightdm"}
        with pytest.raises(ConfigValidationError, match="desktop.dm"):
            validate_config(data)

    def test_valid_desktop_dm_auto(self) -> None:
        data = yaml.safe_load(VALID_CONFIG)
        data["desktop"] = {"profile": "gnome", "dm": "auto"}
        validate_config(data)


# ---------------------------------------------------------------------------
# Phase 3 — load_config additional branches
# ---------------------------------------------------------------------------


class TestLoadConfigBranches:
    def test_plaintext_password_hashed_on_load(self, tmp_path: Path) -> None:
        """load_config must hash a plaintext password via openssl and set password_plaintext."""
        content = """\
            disk:
              device: /dev/vda
            locale:
              timezone: UTC
            network:
              hostname: myhost
            user:
              username: alice
              password: supersecret
        """
        path = _write_yaml(tmp_path, content)
        cfg = load_config(path)
        # Hash must look like a SHA-512 crypt hash
        assert cfg.user.password_hash.startswith("$6$")
        assert cfg.user.password_plaintext == "supersecret"

    def test_invalid_post_install_action_raises(self, tmp_path: Path) -> None:
        import textwrap as _tw
        content = _tw.dedent(VALID_CONFIG) + "\npost_install_action: hibernate\n"
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ConfigValidationError, match="post_install_action"):
            load_config(path)

    def test_post_install_action_shutdown(self, tmp_path: Path) -> None:
        import textwrap as _tw
        content = _tw.dedent(VALID_CONFIG) + "\npost_install_action: shutdown\n"
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.post_install_action == "shutdown"

    def test_desktop_loaded(self, tmp_path: Path) -> None:
        import textwrap as _tw
        content = _tw.dedent(VALID_CONFIG) + "\ndesktop:\n  profile: hyprland\n  dm: sddm\n"
        path = tmp_path / "cfg.yaml"
        path.write_text(content, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.desktop.profile == "hyprland"
        assert cfg.desktop.dm == "sddm"


# ---------------------------------------------------------------------------
# Phase 3 — find_unattended_config tests
# ---------------------------------------------------------------------------


class TestFindUnattendedConfig:
    def test_returns_none_when_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when no standard config paths exist."""
        # Patch out /proc/cmdline and known paths to avoid side effects
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        result = find_unattended_config()
        assert result is None

    def test_finds_config_in_tmp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finds /tmp/ouroborOS-config.yaml when present."""
        fake_config = tmp_path / "ouroborOS-config.yaml"
        fake_config.write_text("key: value", encoding="utf-8")

        from installer import config as config_mod
        from pathlib import Path as OrigPath

        # Patch the known paths inside find_unattended_config to redirect to tmp_path
        original_exists = OrigPath.exists

        def patched_exists(self: OrigPath) -> bool:
            if str(self) == "/tmp/ouroborOS-config.yaml":
                return True
            if str(self).startswith("/proc/cmdline"):
                return False
            if str(self).startswith("/run/ouroborOS"):
                return False
            return original_exists(self)

        monkeypatch.setattr(OrigPath, "exists", patched_exists)

        # Also mock read_text for /proc/cmdline to avoid OSError
        original_read_text = OrigPath.read_text

        def patched_read_text(self: OrigPath, **kwargs: object) -> str:
            if str(self) == "/proc/cmdline":
                return ""
            return original_read_text(self, **kwargs)

        monkeypatch.setattr(OrigPath, "read_text", patched_read_text)

        result = find_unattended_config()
        assert result is not None
        assert str(result) == "/tmp/ouroborOS-config.yaml"

    def test_returns_none_when_media_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: PLR0912
        """Returns None when /run/media is not a directory and no other paths exist."""
        from pathlib import Path as OrigPath

        original_read_text = OrigPath.read_text
        original_exists = OrigPath.exists
        original_is_dir = OrigPath.is_dir

        def patched_read_text(self: OrigPath, **kwargs: object) -> str:
            if str(self) == "/proc/cmdline":
                return ""
            return original_read_text(self, **kwargs)

        def patched_exists(self: OrigPath) -> bool:
            if str(self) in ("/tmp/ouroborOS-config.yaml", "/run/ouroborOS-config.yaml"):
                return False
            return original_exists(self)

        def patched_is_dir(self: OrigPath) -> bool:
            if str(self) == "/run/media":
                return False
            return original_is_dir(self)

        monkeypatch.setattr(OrigPath, "read_text", patched_read_text)
        monkeypatch.setattr(OrigPath, "exists", patched_exists)
        monkeypatch.setattr(OrigPath, "is_dir", patched_is_dir)

        result = find_unattended_config()
        assert result is None


# ---------------------------------------------------------------------------
# load_config_from_url tests
# ---------------------------------------------------------------------------


class TestLoadConfigFromUrl:
    def test_downloads_and_parses_valid_config(self, tmp_path: Path) -> None:
        """load_config_from_url must download YAML and return InstallerConfig."""
        import io
        import textwrap
        import urllib.error

        valid_yaml = textwrap.dedent(VALID_CONFIG).encode("utf-8")

        class FakeResponse:
            status = 200
            def read(self):
                return valid_yaml
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("installer.config.urllib.request.urlopen", return_value=FakeResponse()), \
             patch("installer.config.urllib.request.Request") as mock_req:
            cfg = load_config_from_url("https://example.com/config.yaml")

        assert isinstance(cfg, InstallerConfig)
        assert cfg.disk.device == "/dev/sda"
        assert cfg.unattended is True

    def test_non_mapping_yaml_raises(self) -> None:
        """Remote config that parses to a non-dict must raise ConfigValidationError."""
        bad_yaml = b"- item1\n- item2\n"

        class FakeResponse:
            status = 200
            def read(self):
                return bad_yaml
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("installer.config.urllib.request.urlopen", return_value=FakeResponse()):
            with pytest.raises(ConfigValidationError, match="mapping"):
                load_config_from_url("https://example.com/bad.yaml")

    def test_http_error_response_raises(self) -> None:
        """Covers line 379: HTTP non-200 raises ConfigValidationError."""
        class FakeResponse:
            status = 404
            def read(self):
                return b""
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("installer.config.urllib.request.urlopen", return_value=FakeResponse()):
            with pytest.raises(ConfigValidationError, match="404"):
                load_config_from_url("https://example.com/notfound.yaml")


# ---------------------------------------------------------------------------
# find_unattended_config — cmdline path (lines 416-420)
# ---------------------------------------------------------------------------


class TestFindUnattendedConfigCmdline:
    def test_reads_kernel_cmdline_path_v2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Covers lines 416-420: ouroborOS.config= in /proc/cmdline returns that path."""
        fake_config = tmp_path / "my-config.yaml"
        fake_config.write_text("key: value", encoding="utf-8")

        from pathlib import Path as OrigPath

        original_read_text = OrigPath.read_text
        original_exists = OrigPath.exists

        def patched_read_text(self: OrigPath, **kwargs: object) -> str:
            if str(self) == "/proc/cmdline":
                return f"root=/dev/vda ouroborOS.config={fake_config} quiet"
            return original_read_text(self, **kwargs)

        def patched_exists(self: OrigPath) -> bool:
            if str(self) == str(fake_config):
                return True
            if str(self) in ("/tmp/ouroborOS-config.yaml", "/run/ouroborOS-config.yaml"):
                return False
            return original_exists(self)

        monkeypatch.setattr(OrigPath, "read_text", patched_read_text)
        monkeypatch.setattr(OrigPath, "exists", patched_exists)

        result = find_unattended_config()
        assert result is not None
        assert str(result) == str(fake_config)
