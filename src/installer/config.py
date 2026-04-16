"""config.py — ouroborOS installer configuration model and YAML parser.

InstallerConfig is the single source of truth for all installation parameters.
It is populated from either TUI interaction or an unattended YAML config file.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from installer.desktop_profiles import (
    VALID_DMS,
    VALID_KDE_FLAVORS,
    VALID_PROFILES,
    VALID_SHELLS,
    aur_packages_for,
    shell_path,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class NetworkConfig:
    """Network configuration for the installed system."""

    hostname: str = "ouroboros"
    enable_networkd: bool = True
    enable_iwd: bool = True
    enable_resolved: bool = True

    # WiFi pre-configuration (unattended installs / first-boot).
    # These fields are transient — written to /var/lib/iwd/*.psk (chmod 600)
    # during CONFIGURE state, then cleared from the checkpoint.
    # If wifi_ssid is set, wifi_passphrase is required.
    wifi_ssid: str = ""
    wifi_passphrase: str = ""  # Transient — cleared after iwd PSK is written

    # Bluetooth: enable bluetooth.service post-install (requires bluez).
    bluetooth_enable: bool = False


@dataclass
class UserConfig:
    """Primary user account configuration."""

    username: str = ""
    password_hash: str = ""          # SHA-512 crypt hash — never plaintext
    password_plaintext: str = ""     # Transient — cleared after configure.sh; only for homed migration
    groups: list[str] = field(
        default_factory=lambda: ["wheel", "audio", "video", "input"]
    )
    shell: str = "/bin/bash"
    create_home: bool = True
    # systemd-homed storage backend: "subvolume" (Btrfs, default) | "luks"
    # | "directory" | "classic" (legacy /etc/passwd, opt-out).
    homed_storage: str = "subvolume"


@dataclass
class DesktopConfig:
    """Desktop environment profile — package set only, no curation."""

    profile: str = "minimal"      # minimal | hyprland | niri | gnome | kde | cosmic
    dm: str = "auto"              # auto | gdm | sddm | plm | greetd | none
    kde_flavor: str = "plasma-meta"  # plasma | plasma-meta | plasma-desktop (KDE only)
    gpu_driver: str = "auto"      # auto | mesa | amdgpu | nvidia | nvidia-open | none
    # AUR packages resolved from the profile at load time (not stored in YAML).
    # Populated by load_config() / _build_config() from desktop_profiles.
    # Passed to ouroboros-firstboot for lazy build via our-aur.
    aur_packages: list = field(default_factory=list)


@dataclass
class DiskConfig:
    """Disk and filesystem configuration."""

    device: str = ""                 # e.g. /dev/sda (never /dev/sdX in fstab)
    use_luks: bool = False
    luks_passphrase: str = ""        # cleared after encrypt_partition() is called
    btrfs_label: str = "ouroborOS"
    swap_type: str = "zram"          # "zram" or "none"


@dataclass
class LocaleConfig:
    """Locale, timezone, and keyboard configuration."""

    locale: str = "en_US.UTF-8"
    keymap: str = "us"
    timezone: str = "UTC"
    language: str = "en_US"  # TUI language; one of SUPPORTED_LANGUAGES in i18n.py


@dataclass
class SecurityConfig:
    """Security configuration: Secure Boot + TPM2 + FIDO2 PAM integration."""

    secure_boot: bool = False
    # Include Microsoft OEM keys when enrolling (sbctl enroll-keys -m).
    # Required for dual-boot systems or hardware with pre-signed Option ROMs.
    sbctl_include_ms_keys: bool = False

    # TPM2 auto-unlock for LUKS.
    # When true, binds the LUKS slot to TPM2 PCRs 7+14 (Secure Boot state +
    # systemd-boot measured boot). Requires use_luks: true.
    # Falls back to passphrase if TPM2 is absent or measurements change.
    tpm2_unlock: bool = False

    # FIDO2 PAM integration.
    # When true, installs pam-u2f and configures /etc/pam.d/sudo + login
    # to accept a FIDO2 hardware token as authentication factor (sufficient).
    # The user must register their token post-install with:
    #   our-fido2 pam register --system
    fido2_pam: bool = False


@dataclass
class InstallerConfig:
    """Complete installation configuration.

    This dataclass is serialised to JSON as a checkpoint after every
    state transition so the installer can resume if interrupted.
    """

    disk: DiskConfig = field(default_factory=DiskConfig)
    locale: LocaleConfig = field(default_factory=LocaleConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    user: UserConfig = field(default_factory=UserConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Runtime state — not persisted to YAML config
    install_target: str = "/mnt"
    extra_packages: list[str] = field(default_factory=list)
    enable_luks: bool = False
    unattended: bool = False
    post_install_action: str = "reboot"  # "reboot" | "shutdown" | "none"


# ---------------------------------------------------------------------------
# YAML schema validation
# ---------------------------------------------------------------------------

# Required keys in an unattended config file
_REQUIRED_KEYS: set[str] = {"disk", "locale", "network", "user"}

# Valid timezone pattern (basic check — full validation via /usr/share/zoneinfo)
_TIMEZONE_RE = re.compile(r"^[A-Za-z_]+(/[A-Za-z_]+)*$")

# Valid username (POSIX portable)
_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

# Valid hostname (RFC 1123)
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")


class ConfigValidationError(ValueError):
    """Raised when an installer config file fails validation."""


def _require(mapping: dict, key: str, parent: str = "") -> object:
    """Return mapping[key] or raise ConfigValidationError."""
    path = f"{parent}.{key}" if parent else key
    if key not in mapping:
        raise ConfigValidationError(f"Missing required field: '{path}'")
    return mapping[key]


def validate_config(data: dict) -> None:
    """Validate a parsed YAML config dictionary.

    Raises ConfigValidationError with a descriptive message on the first
    violation found.
    """
    for key in _REQUIRED_KEYS:
        if key not in data:
            raise ConfigValidationError(f"Missing required top-level key: '{key}'")

    # disk section
    disk = data["disk"]
    device = _require(disk, "device", "disk")
    if not isinstance(device, str) or not device.startswith("/dev/"):
        raise ConfigValidationError(
            f"disk.device must be an absolute /dev/ path, got: {device!r}"
        )
    if re.match(r"^/dev/sd[a-z]\d+", str(device)):
        raise ConfigValidationError(
            "disk.device must reference a whole disk, not a partition"
            " (e.g. /dev/sda not /dev/sda1)"
        )

    # locale section
    locale = data["locale"]
    tz = _require(locale, "timezone", "locale")
    if not _TIMEZONE_RE.match(str(tz)):
        raise ConfigValidationError(f"locale.timezone format invalid: {tz!r}")
    _valid_languages = {"en_US", "es_AR", "de_DE", "en", "es", "de"}
    lang = locale.get("language", "en_US")
    if lang not in _valid_languages:
        raise ConfigValidationError(
            f"locale.language must be one of {sorted(_valid_languages)}, got: {lang!r}"
        )

    # network section
    network = data["network"]
    hostname = _require(network, "hostname", "network")
    if not _HOSTNAME_RE.match(str(hostname)):
        raise ConfigValidationError(
            f"network.hostname is not a valid hostname: {hostname!r}"
        )
    wifi = network.get("wifi", {}) or {}
    if wifi:
        wifi_ssid = wifi.get("ssid", "")
        wifi_pass = wifi.get("passphrase", "")
        if wifi_ssid and not wifi_pass:
            raise ConfigValidationError(
                "network.wifi.passphrase is required when network.wifi.ssid is set"
            )
        if wifi_pass and not wifi_ssid:
            raise ConfigValidationError(
                "network.wifi.ssid is required when network.wifi.passphrase is set"
            )

    # user section
    user = data["user"]
    username = _require(user, "username", "user")
    if not _USERNAME_RE.match(str(username)):
        raise ConfigValidationError(
            f"user.username must be a valid POSIX username: {username!r}"
        )
    if "password_hash" not in user and "password" not in user:
        raise ConfigValidationError(
            "user section must include 'password_hash' (SHA-512 crypt) or 'password'"
        )
    homed_storage = user.get("homed_storage", "subvolume")
    if homed_storage not in ("subvolume", "luks", "directory", "classic"):
        raise ConfigValidationError(
            f"user.homed_storage must be one of "
            f"'subvolume'|'luks'|'directory'|'classic', got: {homed_storage!r}"
        )
    # shell (top-level, optional — defaults to "bash")
    shell = data.get("shell", "bash")
    if shell not in VALID_SHELLS:
        raise ConfigValidationError(
            f"shell must be one of {sorted(VALID_SHELLS)}, got: {shell!r}"
        )

    # security section (optional — defaults to secure_boot: false)
    security = data.get("security", {}) or {}
    if security:
        secure_boot = security.get("secure_boot", False)
        if not isinstance(secure_boot, bool):
            raise ConfigValidationError(
                "security.secure_boot must be a boolean (true/false)"
            )
        fido2_pam = security.get("fido2_pam", False)
        if not isinstance(fido2_pam, bool):
            raise ConfigValidationError(
                "security.fido2_pam must be a boolean (true/false)"
            )
        tpm2_unlock = security.get("tpm2_unlock", False)
        if not isinstance(tpm2_unlock, bool):
            raise ConfigValidationError(
                "security.tpm2_unlock must be a boolean (true/false)"
            )
        if tpm2_unlock and not data.get("disk", {}).get("use_luks", False):
            raise ConfigValidationError(
                "security.tpm2_unlock requires disk.use_luks: true"
            )

    # desktop section (optional — defaults to 'minimal')
    desktop = data.get("desktop", {})
    if desktop:
        profile = desktop.get("profile", "minimal")
        if profile not in VALID_PROFILES:
            raise ConfigValidationError(
                f"desktop.profile must be one of {sorted(VALID_PROFILES)}, "
                f"got: {profile!r}"
            )
        dm = desktop.get("dm", "auto")
        if dm not in VALID_DMS and dm != "auto":
            raise ConfigValidationError(
                f"desktop.dm must be one of {sorted(VALID_DMS)} or 'auto', "
                f"got: {dm!r}"
            )
        kde_flavor = desktop.get("kde_flavor", "plasma-meta")
        if kde_flavor not in VALID_KDE_FLAVORS:
            raise ConfigValidationError(
                f"desktop.kde_flavor must be one of {sorted(VALID_KDE_FLAVORS)}, "
                f"got: {kde_flavor!r}"
            )
        gpu_driver = desktop.get("gpu_driver", "auto")
        _valid_gpu = {"auto", "mesa", "amdgpu", "nvidia", "nvidia-open", "none"}
        if gpu_driver not in _valid_gpu:
            raise ConfigValidationError(
                f"desktop.gpu_driver must be one of {sorted(_valid_gpu)}, "
                f"got: {gpu_driver!r}"
            )


# ---------------------------------------------------------------------------
# YAML config loader
# ---------------------------------------------------------------------------


def load_config(path: Path) -> InstallerConfig:
    """Load and validate an unattended install config YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A fully-populated InstallerConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigValidationError: If the config fails validation.
        yaml.YAMLError: If the file is not valid YAML.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ConfigValidationError(
            "Config file must be a YAML mapping at the top level."
        )

    validate_config(data)

    cfg = InstallerConfig()

    # Disk
    d = data["disk"]
    cfg.disk.device = d["device"]
    cfg.disk.use_luks = bool(d.get("use_luks", False))
    cfg.disk.btrfs_label = str(d.get("btrfs_label", "ouroborOS"))
    cfg.disk.swap_type = str(d.get("swap_type", "zram"))
    cfg.enable_luks = cfg.disk.use_luks

    # Locale
    loc = data["locale"]
    cfg.locale.locale = str(loc.get("locale", "en_US.UTF-8"))
    cfg.locale.keymap = str(loc.get("keymap", "us"))
    cfg.locale.timezone = str(loc["timezone"])
    cfg.locale.language = str(loc.get("language", "en_US"))

    # Network
    net = data["network"]
    cfg.network.hostname = str(net["hostname"])
    cfg.network.enable_networkd = bool(net.get("enable_networkd", True))
    cfg.network.enable_iwd = bool(net.get("enable_iwd", True))
    cfg.network.enable_resolved = bool(net.get("enable_resolved", True))
    wifi_cfg = net.get("wifi", {}) or {}
    cfg.network.wifi_ssid = str(wifi_cfg.get("ssid", ""))
    cfg.network.wifi_passphrase = str(wifi_cfg.get("passphrase", ""))
    bt_cfg = net.get("bluetooth", {}) or {}
    cfg.network.bluetooth_enable = bool(bt_cfg.get("enable", False))

    # User
    usr = data["user"]
    cfg.user.username = str(usr["username"])
    if "password_hash" in usr:
        cfg.user.password_hash = str(usr["password_hash"])
    elif "password" in usr:
        plaintext = str(usr["password"])
        result = subprocess.run(
            ["openssl", "passwd", "-6", "-stdin"],
            input=plaintext,
            capture_output=True,
            text=True,
            check=True,
        )
        cfg.user.password_hash = result.stdout.strip()
        cfg.user.password_plaintext = plaintext
    cfg.user.groups = list(usr.get("groups", ["wheel", "audio", "video", "input"]))
    cfg.user.shell = shell_path(str(data.get("shell", "bash")))
    cfg.user.homed_storage = str(usr.get("homed_storage", "subvolume"))

    # Desktop profile (optional)
    desk = data.get("desktop", {}) or {}
    cfg.desktop.profile = str(desk.get("profile", "minimal"))
    cfg.desktop.dm = str(desk.get("dm", "auto"))
    cfg.desktop.kde_flavor = str(desk.get("kde_flavor", "plasma-meta"))
    cfg.desktop.gpu_driver = str(desk.get("gpu_driver", "auto"))
    cfg.desktop.aur_packages = aur_packages_for(cfg.desktop.profile)

    # Security (optional)
    sec = data.get("security", {}) or {}
    cfg.security.secure_boot = bool(sec.get("secure_boot", False))
    cfg.security.sbctl_include_ms_keys = bool(sec.get("sbctl_include_ms_keys", False))
    cfg.security.tpm2_unlock = bool(sec.get("tpm2_unlock", False))
    cfg.security.fido2_pam = bool(sec.get("fido2_pam", False))

    # Extra packages
    cfg.extra_packages = list(data.get("extra_packages", []))
    cfg.unattended = True

    # Post-install action (optional — defaults to "reboot")
    action = str(data.get("post_install_action", "reboot")).lower()
    if action not in ("reboot", "shutdown", "none"):
        raise ConfigValidationError(
            f"Invalid post_install_action: '{action}'. "
            "Must be 'reboot', 'shutdown', or 'none'."
        )
    cfg.post_install_action = action

    return cfg


def load_config_from_url(url: str) -> InstallerConfig:
    """Download a YAML config from a URL and load it.

    Args:
        url: HTTP(S) URL to a YAML config file.

    Returns:
        A fully-populated InstallerConfig instance.

    Raises:
        ConfigValidationError: If the downloaded config fails validation.
        urllib.error.URLError: If the download fails.
    """
    log = logging.getLogger(__name__)
    log.info("Downloading remote config from: %s", url)

    req = urllib.request.Request(url, headers={"User-Agent": "ouroborOS-installer"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise ConfigValidationError(f"Failed to download config: HTTP {resp.status}")
        raw = resp.read().decode("utf-8")

    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigValidationError("Remote config must be a YAML mapping at the top level.")

    validate_config(data)

    # Save to temp file for reference
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="ouroborOS-remote-",
        dir="/tmp", delete=False, encoding="utf-8"
    )
    tmp.write(raw)
    tmp.close()

    return load_config(Path(tmp.name))


def find_unattended_config() -> Path | None:
    """Search standard locations for an unattended install config.

    Search order:
    1. Kernel cmdline: ``ouroborOS.config=/path/to/config.yaml``
    2. /tmp/ouroborOS-config.yaml  (e.g. injected via cloud-init or live ISO)
    3. /run/ouroborOS-config.yaml
    4. First *.yaml on USB drives under /run/media/

    Returns:
        Path to a config file if found, else None.
    """
    # 1. Kernel cmdline
    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
        for token in cmdline.split():
            if token.startswith("ouroborOS.config="):
                candidate = Path(token.split("=", 1)[1])
                if candidate.exists():
                    return candidate
    except OSError:
        pass

    # 2 & 3. Known temp paths
    for candidate in (
        Path("/tmp/ouroborOS-config.yaml"),
        Path("/run/ouroborOS-config.yaml"),
    ):
        if candidate.exists():
            return candidate

    # 4. USB drives
    media_root = Path("/run/media")
    if media_root.is_dir():
        for yaml_file in sorted(media_root.rglob("*.yaml")):
            if yaml_file.stem in ("ouroborOS-config", "ouroborOS", "installer-config"):
                return yaml_file

    return None
