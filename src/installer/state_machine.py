"""state_machine.py — ouroborOS installer finite state machine.

The installer is modelled as a linear FSM with checkpointing.
Each state corresponds to one installation phase. If the installer
is interrupted, it can resume from the last completed checkpoint.

State flow:
    INIT → NETWORK_SETUP → PREFLIGHT → LOCALE → USER → DESKTOP
         → SECURE_BOOT → PARTITION → FORMAT → INSTALL
         → CONFIGURE → SNAPSHOT → FINISH

Error states:
    Any state can transition to ERROR_RECOVERABLE (retry) or FATAL (abort).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from enum import Enum, auto
from pathlib import Path

from installer.config import InstallerConfig, find_unattended_config, load_config, load_config_from_url
from installer.desktop_profiles import (
    aur_packages_for,
    dm_package,
    dm_service,
    packages_for,
    resolve_dm,
    shell_package,
    shell_path,
)
from installer.i18n import _, init_i18n

try:
    from installer.tui_textual import TUI  # type: ignore[import]
except ImportError:
    from installer.tui import TUI  # type: ignore[import]  # noqa: F401

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = Path("/tmp/ouroborOS-install.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)

log = logging.getLogger("installer")


def _read_iso_version() -> str:
    """Read iso_version from the profiledef.sh installed on the live ISO."""
    candidates = [
        Path("/usr/lib/ouroborOS/installer/profiledef.sh"),
        Path("/home/hbuddenberg/developments/ouroborOS/src/ouroborOS-profile/profiledef.sh"),
    ]
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            m = re.search(r'iso_version="([^"]+)"', text)
            if m:
                return m.group(1)
    return "rolling"

# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class State(Enum):

    INIT = auto()
    NETWORK_SETUP = auto()
    PREFLIGHT = auto()
    LOCALE = auto()
    USER = auto()
    DESKTOP = auto()
    DOTS_PACK = auto()
    SECURE_BOOT = auto()
    PARTITION = auto()
    FORMAT = auto()
    INSTALL = auto()
    CONFIGURE = auto()
    SNAPSHOT = auto()
    FINISH = auto()
    ERROR_RECOVERABLE = auto()
    FATAL = auto()


# State execution order (excludes error states).
#
# IMPORTANT: every state that requires human input (LOCALE, USER, DESKTOP,
# PARTITION confirmation) runs BEFORE FORMAT. Once FORMAT begins, the disk
# is wiped — we never ask the user anything after that point.
_STATE_ORDER: list[State] = [
    State.INIT,
    State.NETWORK_SETUP,
    State.PREFLIGHT,
    State.LOCALE,
    State.USER,
    State.DESKTOP,
    State.DOTS_PACK,
    State.SECURE_BOOT,
    State.PARTITION,
    State.FORMAT,
    State.INSTALL,
    State.CONFIGURE,
    State.SNAPSHOT,
    State.FINISH,
]

_STEP_RANGES: dict[State, tuple[int, int]] = {
    State.INIT: (0, 3),
    State.NETWORK_SETUP: (3, 6),
    State.PREFLIGHT: (6, 10),
    State.LOCALE: (10, 14),
    State.USER: (14, 17),
    State.DESKTOP: (17, 21),
    State.DOTS_PACK: (21, 23),
    State.SECURE_BOOT: (23, 25),
    State.PARTITION: (25, 30),
    State.FORMAT: (30, 45),
    State.INSTALL: (45, 70),
    State.CONFIGURE: (70, 90),
    State.SNAPSHOT: (90, 95),
    State.FINISH: (95, 100),
}

_STEP_LABELS: dict[State, str] = {
    State.INIT: "Initializing",
    State.NETWORK_SETUP: "Connecting to network",
    State.PREFLIGHT: "Checking requirements",
    State.LOCALE: "Configuring language",
    State.USER: "Creating user",
    State.DESKTOP: "Selecting desktop",
    State.DOTS_PACK: "Selecting dotfiles pack",
    State.SECURE_BOOT: "Configuring Secure Boot",
    State.PARTITION: "Selecting disk",
    State.FORMAT: "Preparing disk",
    State.INSTALL: "Installing packages",
    State.CONFIGURE: "Configuring system",
    State.SNAPSHOT: "Creating snapshot",
    State.FINISH: "Finishing",
}

# ---------------------------------------------------------------------------
# Checkpoint system
# ---------------------------------------------------------------------------

CHECKPOINT_DIR = Path("/tmp/ouroborOS-checkpoints")


def _checkpoint_path(state: State) -> Path:
    """Return the checkpoint file path for a state."""
    return CHECKPOINT_DIR / f"{state.name.lower()}.done"


def _save_checkpoint(state: State, config: InstallerConfig) -> None:
    """Mark a state as completed and persist config to disk."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(state).write_text("done", encoding="utf-8")
    config_path = CHECKPOINT_DIR / "config.json"
    config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    log.debug("Checkpoint saved: %s", state.name)


def _is_completed(state: State) -> bool:
    """Return True if the checkpoint for this state exists."""
    return _checkpoint_path(state).exists()


def _load_config_checkpoint() -> InstallerConfig | None:
    """Load a previously-saved InstallerConfig from the checkpoint directory."""
    config_path = CHECKPOINT_DIR / "config.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        cfg = InstallerConfig()
        # Manually restore nested dataclass fields from the flat dict
        for key, value in data.items():
            if hasattr(cfg, key) and isinstance(value, dict):
                sub = getattr(cfg, key)
                for k, v in value.items():
                    if hasattr(sub, k):
                        setattr(sub, k, v)
            elif hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("Failed to load config checkpoint: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Installer class
# ---------------------------------------------------------------------------

OPS_DIR = Path(__file__).parent / "ops"


class InstallerError(Exception):
    """Raised for recoverable installation errors."""


class FatalError(Exception):
    """Raised for unrecoverable installation errors."""


class Installer:
    """ouroborOS installer finite state machine.

    Attributes:
        config: Current installation configuration.
        state:  Current FSM state.
        tui:    TUI interface (or None in unattended mode).
    """

    def __init__(self, resume: bool = False, config_path: Path | None = None) -> None:
        self.state: State = State.INIT
        self.config: InstallerConfig = InstallerConfig()
        self.tui: TUI | None = None
        self._resume = resume
        self._config_path = config_path
        self._handler_map: dict[State, Callable[[], None]] = {
            State.INIT: self._handle_init,
            State.NETWORK_SETUP: self._handle_network_setup,
            State.PREFLIGHT: self._handle_preflight,
            State.LOCALE: self._handle_locale,
            State.USER: self._handle_user,
            State.DESKTOP: self._handle_desktop,
            State.DOTS_PACK: self._handle_dots_pack,
            State.SECURE_BOOT: self._handle_secure_boot,
            State.PARTITION: self._handle_partition,
            State.FORMAT: self._handle_format,
            State.INSTALL: self._handle_install,
            State.CONFIGURE: self._handle_configure,
            State.SNAPSHOT: self._handle_snapshot,
            State.FINISH: self._handle_finish,
        }

    # --- Public entry point -------------------------------------------------

    def run(self) -> int:
        """Run the installer FSM from current state to FINISH.

        Returns:
            0 on success, 1 on failure.
        """
        log.info("ouroborOS installer starting (PID %d)", os.getpid())
        log.info("Log file: %s", LOG_FILE)

        try:
            for state in _STATE_ORDER:
                self.state = state

                if self._resume and _is_completed(state):
                    log.info("Skipping completed state: %s", state.name)
                    # Restore config from checkpoint
                    saved = _load_config_checkpoint()
                    if saved is not None:
                        self.config = saved
                    continue

                log.info("Entering state: %s", state.name)
                handler = self._handler_map[state]

                retries = 0
                max_retries = 3
                while True:
                    try:
                        handler()
                        _save_checkpoint(state, self.config)
                        log.info("State completed: %s", state.name)
                        if state == State.INIT and self.tui:
                            self.tui.start_install_progress()
                            self._update_progress(State.INIT, 100)
                        break
                    except InstallerError as exc:
                        retries += 1
                        log.warning("Recoverable error in %s: %s", state.name, exc)
                        if retries >= max_retries:
                            raise FatalError(
                                f"Too many retries in state {state.name}: {exc}"
                            ) from exc
                        if self.tui:
                            retry = self.tui.show_error(str(exc), recoverable=True)
                            if not retry:
                                raise FatalError(
                                    f"User aborted at state {state.name}."
                                ) from exc
                        else:
                            log.error("Unattended mode: aborting on error.")
                            raise FatalError(str(exc)) from exc

        except FatalError as exc:
            self.state = State.FATAL
            log.critical("Fatal error: %s", exc)
            if self.tui:
                self.tui.stop_install_progress()
                self.tui.show_error(str(exc), recoverable=False)
            return 1
        except KeyboardInterrupt:
            self.state = State.FATAL
            log.warning("Installation interrupted by user.")
            if self.tui:
                self.tui.stop_install_progress()
                self.tui.show_error(
                    "Installation cancelled by user.", recoverable=False
                )
            return 1

        return 0

    # --- State handlers -----------------------------------------------------

    def _update_progress(self, state: State, sub_pct: int, detail: str = "") -> None:
        lo, hi = _STEP_RANGES[state]
        global_pct = lo + int((hi - lo) * max(0, min(100, sub_pct)) / 100)
        step_num = _STATE_ORDER.index(state) + 1
        total = len(_STATE_ORDER)
        label = _(_STEP_LABELS.get(state, state.name))
        if self.tui:
            self.tui.update_install_progress(
                global_pct, step_num, total, label, detail,
                phase=state.name, sub_pct=int(max(0, min(100, sub_pct))),
            )

    def _handle_init(self) -> None:
        """INIT — detect unattended mode or initialise TUI.

        Bug B fix (2026-06-10): When an unattended config is detected AND a
        TTY is available, the user is asked whether to use the config (silent
        install) or proceed to the interactive TUI menu. If no TTY (true CI/E2E
        boot), the config is used directly to preserve automation.
        """
        config_path = self._config_path or find_unattended_config()
        if config_path:
            log.info("Unattended config found: %s", config_path)
            # Ask user before going silent — only if a TTY is available
            if sys.stdin.isatty() and not os.environ.get("OUROBOROS_FORCE_UNATTENDED"):
                print(f"\n[unattended config detected at: {config_path}]")
                try:
                    answer = input("Use this config for silent install? [Y/n] (n = interactive menu): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "y"
                if answer in ("n", "no"):
                    log.info("User chose interactive mode — ignoring unattended config.")
                    config_path = None
            if config_path:
                self.config = load_config(config_path)
                self.tui = None
                return

        # No config found — start interactive TUI
        self.tui = TUI(title="ouroborOS Installer")

        # Language selection is the very first screen — before welcome.
        # i18n is not yet initialised; show_language_selection() uses hardcoded strings.
        lang = self.tui.show_language_selection()
        self.config.locale.language = lang
        init_i18n(lang)
        log.info("Installer language set to: %s", lang)

        self.tui.show_welcome()

        # Ask if user wants to provide a remote config URL
        remote_url = self.tui.show_remote_config_prompt()
        if remote_url:
            try:
                self.config = load_config_from_url(remote_url)
                self.tui = None  # Switch to unattended mode
                log.info("Remote config loaded successfully from: %s", remote_url)
            except Exception as exc:
                log.warning("Failed to load remote config: %s", exc)
                if self.tui:
                    self.tui.show_error(
                        f"Failed to load remote config:\n{exc}\n\n"
                        "Continuing in interactive mode.",
                        recoverable=True,
                    )
                # Fall through to interactive mode — TUI is still alive

    def _handle_network_setup(self) -> None:
        """NETWORK_SETUP — detect connectivity, offer WiFi if offline."""
        self._update_progress(State.NETWORK_SETUP, 0, "Verificando conexión...")

        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            log.info("Network already online — skipping WiFi setup")
            self._update_progress(State.NETWORK_SETUP, 100, "Conexión establecida")
            return

        log.info("No internet connectivity detected")
        if self.tui is not None:
            wifi_creds = self.tui.show_wifi_connect()
            if wifi_creds is not None:
                self.config.network.wifi_ssid = wifi_creds["ssid"]
                self.config.network.wifi_passphrase = wifi_creds["passphrase"]
                log.info("WiFi credentials captured: %s", wifi_creds["ssid"])

        self._update_progress(State.NETWORK_SETUP, 100, "Red configurada")

    def _handle_preflight(self) -> None:
        """PREFLIGHT — verify system requirements."""
        checks: list[tuple[str, object]] = [
            ("UEFI mode", self._check_uefi),
            ("Root privileges", self._check_root),
            ("Required tools", self._check_tools),
            ("Minimum RAM (1 GiB)", self._check_ram),
        ]
        if not self._has_internet() and self._detect_offline_cache():
            log.info("No internet + offline cache detected — skipping connectivity check")
        else:
            checks.append(("Internet connectivity", self._check_network))

        self._update_progress(State.PREFLIGHT, 0, "Iniciando verificación...")

        failed = []
        for i, (name, check_fn) in enumerate(checks):
            try:
                check_fn()
                log.info("Preflight check passed: %s", name)
            except InstallerError as exc:
                log.warning("Preflight check failed: %s — %s", name, exc)
                failed.append(f"{name}: {exc}")
            self._update_progress(
                State.PREFLIGHT,
                int((i + 1) / len(checks) * 100),
                f"Verificando: {name}",
            )

        if failed:
            raise InstallerError("Preflight checks failed:\n" + "\n".join(failed))

        # Thunderbolt auto-detect — silent, no UI, drives configure.sh
        try:
            tb = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, check=False,
            )
            self.config.hardware.thunderbolt_detected = "thunderbolt" in tb.stdout.lower()
            if self.config.hardware.thunderbolt_detected:
                log.info("Thunderbolt hardware detected — boltd will be enabled during CONFIGURE.")
        except FileNotFoundError:
            log.debug("lspci not available — thunderbolt detection skipped.")

    def _handle_locale(self) -> None:
        """LOCALE — set locale, timezone, keymap."""
        self._update_progress(State.LOCALE, 0)
        if self.tui:
            locale_cfg = self.tui.show_locale_menu()
            self.config.locale.locale = locale_cfg["locale"]
            self.config.locale.keymap = locale_cfg["keymap"]
            self.config.locale.timezone = locale_cfg["timezone"]
            subprocess.run(["loadkeys", self.config.locale.keymap], check=False)
            log.info("Applied keymap '%s' to live environment.", self.config.locale.keymap)
            self.config.network.hostname = self.tui.show_hostname_input()
        log.info(
            "Locale: %s / %s / %s",
            self.config.locale.locale,
            self.config.locale.keymap,
            self.config.locale.timezone,
        )
        self._update_progress(State.LOCALE, 100)

    def _handle_user(self) -> None:
        """USER — collect user accounts and shell BEFORE touching the disk.

        This state used to live inside CONFIGURE (after pacstrap). It was
        moved forward so a cancelled prompt cannot waste a disk wipe.
        Supports multiple users (v0.5.4+) via show_users_creation().
        """
        self._update_progress(State.USER, 0)
        if self.tui:
            from installer.config import UserConfig  # noqa: PLC0415
            user_dicts = self.tui.show_users_creation()
            shell_name = self.tui.show_shell_selection()

            pkg = shell_package(shell_name)
            if pkg and pkg not in self.config.extra_packages:
                self.config.extra_packages.append(pkg)
                log.info("Shell package queued: %s", pkg)

            for ud in user_dicts:
                u = UserConfig()
                u.username = ud["username"]
                u.password_hash = ud["password_hash"]
                u.password_plaintext = ud.get("password", "")
                u.real_name = ud.get("real_name", "")
                is_primary = len(self.config.users) == 0
                default_groups = ["wheel", "audio", "video", "input"] if is_primary else ["audio", "video", "input"]
                _raw_groups = ud.get("groups", default_groups)
                u.groups = _raw_groups if isinstance(_raw_groups, list) else [g for g in _raw_groups.split(",") if g]
                u.shell = shell_path(shell_name)
                u.homed_storage = ud.get("homed_storage", "subvolume")
                self.config.users.append(u)

            # Optional root password (TUI accessor; '' keeps root locked).
            get_root = getattr(self.tui, "get_root_password", None)
            if callable(get_root):
                self.config.security.root_password = get_root()

        log.info(
            "Users configured: %s",
            [u.username for u in self.config.users],
        )
        self._update_progress(State.USER, 100)

    def _detect_gpu(self) -> str:
        """Detect the GPU family via lspci. Returns 'nvidia', 'amdgpu', 'mesa', or 'auto'."""
        result = subprocess.run(["lspci"], capture_output=True, text=True, check=False)
        output = result.stdout.lower()
        if "nvidia" in output:
            return "nvidia"
        if "amd" in output or "radeon" in output:
            return "amdgpu"
        if "intel" in output:
            return "mesa"
        return "auto"

    def _handle_desktop(self) -> None:
        """DESKTOP — pick a desktop profile, display manager, and GPU driver."""
        self._update_progress(State.DESKTOP, 0)
        if self.tui:
            profile = self.tui.show_desktop_selection()
            self.config.desktop.profile = profile
            # F5: derive terminal + filemanager defaults from profile
            self.config.desktop.apply_profile_defaults()
            dm_choice = self.tui.show_dm_selection(profile=profile)
            self.config.desktop.dm = dm_choice
            self.config.desktop.aur_packages = aur_packages_for(profile)

            if profile == "kde":
                self.config.desktop.kde_flavor = self.tui.show_kde_flavor()

            detected_gpu = self._detect_gpu()
            self.config.desktop.gpu_driver = self.tui.show_gpu_selection(detected=detected_gpu)

        log.info(
            "Desktop profile: %s (dm: %s → %s, gpu: %s, kde_flavor: %s)",
            self.config.desktop.profile,
            self.config.desktop.dm,
            resolve_dm(self.config.desktop.profile, self.config.desktop.dm),
            self.config.desktop.gpu_driver,
            self.config.desktop.kde_flavor,
        )
        self._update_progress(State.DESKTOP, 100)

    def _handle_dots_pack(self) -> None:
        """DOTS_PACK — optional dotfiles pack selection.

        Skipped silently under any of these conditions:
        1. Desktop profile is 'minimal'.
        2. No packs are available for the selected profile.
        3. Unattended mode and no pack was configured.
        4. Running offline (packs require internet).
        """
        self._update_progress(State.DOTS_PACK, 0)

        # Condition 1: minimal profile has no desktop, so no packs apply
        if self.config.desktop.profile == "minimal":
            log.info("DOTS_PACK: profile is minimal — skipping.")
            self._update_progress(State.DOTS_PACK, 100)
            return

        # Condition 2: no packs available for this profile (only when manifest dir exists)
        from installer.dots_profiles import MANIFEST_DIR, packs_for_profile  # noqa: PLC0415
        if MANIFEST_DIR.exists():
            available = packs_for_profile(self.config.desktop.profile)
            if not available:
                log.info("DOTS_PACK: no packs available for profile '%s' — skipping.", self.config.desktop.profile)
                self._update_progress(State.DOTS_PACK, 100)
                return

        # Condition 3: unattended mode with no pack selected
        if not self.tui and not self.config.dots_pack.pack:
            log.info("DOTS_PACK: unattended mode, no pack configured — skipping.")
            self._update_progress(State.DOTS_PACK, 100)
            return

        # Condition 4: offline (packs require internet to clone/install)
        if not self._has_internet():
            log.info("DOTS_PACK: no internet connectivity — skipping dotfiles pack selection.")
            self.config.dots_pack.pack = None
            self._update_progress(State.DOTS_PACK, 100)
            return

        if self.tui:
            result = self.tui.show_dots_pack_selection(self.config.desktop.profile)
            self.config.dots_pack.pack = result.get("pack")
            self.config.dots_pack.channel = result.get("channel", "stable")

        # F4-02: auto-correct channel for git-only packs (C-03)
        if self.config.dots_pack.pack:
            import yaml  # noqa: PLC0415
            from installer.dots_profiles import MANIFEST_DIR  # noqa: PLC0415
            mf_path = MANIFEST_DIR / f"{self.config.dots_pack.pack}.yaml"
            if mf_path.exists():
                try:
                    with mf_path.open() as fh:
                        mf_data = yaml.safe_load(fh) or {}
                    variants = mf_data.get("variants") or {}
                    if not variants.get("stable") and variants.get("git"):
                        self.config.dots_pack.channel = "git"
                        log.info(
                            "DOTS_PACK: auto-corrected channel to 'git' for git-only pack '%s'.",
                            self.config.dots_pack.pack,
                        )
                except Exception as exc:  # noqa: BLE001
                    log.debug("DOTS_PACK: could not read manifest for channel correction: %s", exc)

        log.info(
            "Dots pack: %s (channel: %s)",
            self.config.dots_pack.pack or "none",
            self.config.dots_pack.channel,
        )
        self._update_progress(State.DOTS_PACK, 100)

    @staticmethod
    def _detect_existing_os(esp_path: str = "/boot") -> list[str]:
        """Scan the ESP for known OS boot entries.

        Returns a list of human-readable OS names found, e.g. ``["Windows Boot Manager"]``.
        The ESP is typically mounted at /boot or /boot/efi on the live system.
        """
        detected: list[str] = []
        efi_dir = Path(esp_path) / "EFI"
        if not efi_dir.is_dir():
            return detected

        # Windows: look for the Windows Boot Manager EFI binary
        win_efi = efi_dir / "Microsoft" / "Boot" / "bootmgfw.efi"
        if win_efi.exists():
            detected.append("Windows Boot Manager")

        # Other Linux distros: any EFI sub-directory that isn't ours or BOOT
        skip = {"ouroborOS", "ouroboros", "BOOT", "Microsoft", "systemd"}
        for entry in sorted(efi_dir.iterdir()):
            if entry.is_dir() and entry.name not in skip:
                detected.append(f"Linux — {entry.name}")

        return detected

    def _handle_secure_boot(self) -> None:
        """SECURE_BOOT — dual-boot detection + Secure Boot setup instructions."""
        self._update_progress(State.SECURE_BOOT, 0)

        # --- Dual-boot detection (interactive mode only) ---
        if self.tui and not self.config.unattended:
            detected = self._detect_existing_os()
            enable_dual_boot = self.tui.show_dual_boot_prompt(detected)
            self.config.security.dual_boot = enable_dual_boot
            if enable_dual_boot:
                # When dual-booting with Windows + Secure Boot, include MS OEM keys
                if self.config.security.secure_boot and "Windows Boot Manager" in detected:
                    self.config.security.sbctl_include_ms_keys = True
                    log.info("Dual-boot + Secure Boot: sbctl_include_ms_keys set to True (Windows detected).")
            log.info("Dual-boot: %s (detected: %s)", enable_dual_boot, detected)

        if not self.config.security.secure_boot:
            log.info("Secure Boot disabled in config — skipping Secure Boot prompt.")
            self._update_progress(State.SECURE_BOOT, 100)
            return

        if self.tui:
            self.tui.show_secure_boot_prompt()
        log.info("Secure Boot: sbctl setup will run during CONFIGURE (sbctl create-keys + enroll-keys + sign-all).")
        self._update_progress(State.SECURE_BOOT, 100)

    def _handle_partition(self) -> None:
        """PARTITION — disk selection, layout preview, confirmation."""
        self._update_progress(State.PARTITION, 0)
        if self.tui:
            disk = self.tui.show_disk_selection()
            self.config.disk.device = disk
            use_luks = self.tui.show_luks_prompt()
            self.config.disk.use_luks = use_luks
            if use_luks:
                self.config.disk.luks_passphrase = self.tui.show_passphrase_input()
                self.config.security.tpm2_unlock = self.tui.show_tpm2_prompt()
            get_scheme = getattr(self.tui, "get_disk_scheme", None)
            if callable(get_scheme):
                result = get_scheme()
                if isinstance(result, tuple) and len(result) == 2:
                    self.config.disk.partition_scheme = result[0]
                    self.config.disk.manual_partitions = result[1]
            self.tui.show_partition_preview(disk, use_luks)
            confirmed = self.tui.show_confirmation(
                f"WARNING: All data on {disk} will be destroyed. Continue?"
            )
            if not confirmed:
                raise InstallerError("User did not confirm disk wipe. Aborting.")
        log.info(
            "Target disk: %s (LUKS: %s)",
            self.config.disk.device,
            self.config.disk.use_luks,
        )
        self._update_progress(State.PARTITION, 100)

    def _handle_format(self) -> None:
        """FORMAT — partition, format, create subvolumes, mount, fstab."""
        self._update_progress(State.FORMAT, 0, "Preparando disco...")

        args = [
            "bash",
            str(OPS_DIR / "disk.sh"),
            "--action", "prepare_disk",
            "--disk", self.config.disk.device,
            "--target", self.config.install_target,
        ]

        if self.config.disk.use_luks and self.config.disk.luks_passphrase:
            args += ["--luks", self.config.disk.luks_passphrase]

        if self.config.disk.partition_scheme == "manual":
            args += ["--scheme", "manual"]
            for part in self.config.disk.manual_partitions:
                spec = "{number}:{size}:{type}:{mountpoint}:{fs}".format(
                    number=part.get("number", ""),
                    size=part.get("size", ""),
                    type=part.get("type", ""),
                    mountpoint=part.get("mountpoint", ""),
                    fs=part.get("fs", ""),
                )
                args += ["--part", spec]

        self._run_op(args, progress_title="Disk Setup", final_msg="Disk prepared.")
        self._update_progress(State.FORMAT, 100, "Disco preparado")

        self.config.disk.luks_passphrase = ""

    # Reflector args shared across all attempts.
    _REFLECTOR_BASE_ARGS: list[str] = [
        "--protocol", "https,http",
        "--latest", "20",
        "--age", "24",
        "--sort", "score",
        "--number", "10",
    ]

    def _generate_mirrorlist(self) -> None:
        """Generate a working mirrorlist on the live system for pacstrap.

        If config.mirrors is set, write them directly and skip reflector.
        Otherwise: broad pool → score → keep fastest 10.
        """
        host_mirrorlist = Path("/etc/pacman.d/mirrorlist")

        if self.config.mirrors:
            lines = "\n".join(f"Server = {url}/$repo/os/$arch" for url in self.config.mirrors)
            host_mirrorlist.write_text(lines + "\n", encoding="utf-8")
            log.info("Mirrorlist set from config (%d mirrors)", len(self.config.mirrors))
            return

        self._update_progress(State.INSTALL, 0, "Benchmarking mirrors...")

        # Attempt 1: regional (auto-detected by reflector via geoip)
        regional_args = [
            "reflector",
            *self._REFLECTOR_BASE_ARGS,
            "--save", str(host_mirrorlist),
        ]
        result = subprocess.run(
            regional_args, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log.info("Host mirrorlist generated (regional): %s", host_mirrorlist)
            return

        log.warning(
            "reflector (regional) failed: %s — trying worldwide fallback",
            result.stderr.strip(),
        )

        # Attempt 2: worldwide (no country filter)
        worldwide_args = [
            "reflector",
            *self._REFLECTOR_BASE_ARGS,
            "--save", str(host_mirrorlist),
        ]
        result = subprocess.run(
            worldwide_args, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log.info("Host mirrorlist generated (worldwide): %s", host_mirrorlist)
            return

        raise InstallerError(
            f"reflector failed to generate mirrorlist: {result.stderr}"
        )

    def _init_pacman_keyring(self) -> None:
        """Initialise the pacman keyring on the live system.

        pacstrap (without -K/-G) copies the host keyring into the new root.
        The live ISO keyring may not be populated yet, so we init + populate
        once here so that the copy pacstrap makes has valid keys.
        """
        self._update_progress(State.INSTALL, 20, "Inicializando keyring...")

        for step, args in (
            ("init", ["pacman-key", "--init"]),
            ("populate", ["pacman-key", "--populate", "archlinux"]),
        ):
            log.info("Running: %s", " ".join(args))
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                log.warning(
                    "pacman-key %s failed (rc=%d): %s",
                    step,
                    result.returncode,
                    result.stderr.strip(),
                )
                raise InstallerError(
                    f"pacman-key --{step} failed: {result.stderr.strip()}"
                )

        log.info("Pacman keyring initialised.")

    def _detect_microcode_package(self) -> str | None:
        """Return the appropriate microcode package for this CPU, or None."""
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            if "GenuineIntel" in cpuinfo:
                return "intel-ucode"
            if "AuthenticAMD" in cpuinfo:
                return "amd-ucode"
        except OSError:
            pass
        return None

    def _detect_offline_cache(self) -> str | None:
        """Return path to pre-populated package cache if ISO was built with --with-cache."""
        # mkarchiso wipes /var/cache/pacman/pkg — cache lives in a separate path
        cache = Path("/var/cache/ouroboros-offline")
        if cache.is_dir() and any(cache.glob("*.pkg.tar.zst")):
            return str(cache)
        return None

    def _has_internet(self) -> bool:
        """Return True if internet is reachable."""
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def _handle_install(self) -> None:
        """INSTALL — pacstrap base system with automatic retries."""
        target = self.config.install_target

        # Offline mode: skip reflector (needs internet), use ISO default mirrorlist
        if not self._has_internet() and self._detect_offline_cache():
            log.info("Offline mode: skipping mirrorlist generation (using ISO default)")
        else:
            self._generate_mirrorlist()

        self._init_pacman_keyring()

        # Write custom mkinitcpio.conf BEFORE pacstrap so that the linux-zen
        # post-install hook generates a correct initramfs from the start:
        #   - btrfs in MODULES and HOOKS (required for btrfs root)
        #   - no autodetect (chroot has no real btrfs devices, so autodetect
        #     would strip the module)
        mkinitcpio_path = Path(target) / "etc" / "mkinitcpio.conf"
        mkinitcpio_path.parent.mkdir(parents=True, exist_ok=True)
        mkinitcpio_path.write_text(
            "MODULES=(btrfs)\n"
            "BINARIES=()\n"
            "FILES=()\n"
            "HOOKS=(base udev microcode modconf kms keyboard keymap consolefont block btrfs filesystems fsck)\n"
        )
        log.info("Pre-seeded mkinitcpio.conf with btrfs support (no autodetect).")

        packages = [
            "base",
            "linux-zen",
            "linux-zen-headers",
            "linux-firmware",
            "btrfs-progs",
            "arch-install-scripts",
            "systemd",
            "iwd",
            "python",
            "python-yaml",
            "efibootmgr",
            "sudo",
            "zram-generator",
            "which",
            "neovim",
            # systemd-nspawn + machinectl ship with the `systemd` package
            # (already in base), used by `our-container` for container workflows.
        ] + self.config.extra_packages + packages_for(
            self.config.desktop.profile,
            kde_flavor=self.config.desktop.kde_flavor,
        )

        # Remove packages explicitly excluded in config (e.g. for E2E testing)
        if self.config.skip_packages:
            skip = set(self.config.skip_packages)
            packages = [p for p in packages if p not in skip]
            log.info("Skipped packages from config: %s", ", ".join(skip))

        # Add openssh only when explicitly enabled
        if self.config.network.enable_ssh:
            packages.append("openssh")

        # Add sbctl when Secure Boot is enabled
        if self.config.security.secure_boot and "sbctl" not in packages:
            packages.append("sbctl")

        # Add DM package if explicitly chosen and not already in profile packages
        resolved_dm = resolve_dm(self.config.desktop.profile, self.config.desktop.dm)
        if resolved_dm != "none":
            dm_pkg = dm_package(resolved_dm)
            if dm_pkg not in packages:
                packages.append(dm_pkg)

        ucode = self._detect_microcode_package()
        if ucode:
            log.info("Detected CPU microcode package: %s", ucode)
            packages.insert(0, ucode)

        # Capture for system.yaml generation at FINISH
        self.config.installed_packages = list(packages)

        offline_cache = self._detect_offline_cache()
        is_offline = offline_cache and not self._has_internet()
        if offline_cache:
            log.info("Offline package cache detected at %s (no internet mode)", offline_cache)
        if is_offline:
            log.info("Offline mode: no internet, using cache exclusively")
            # pacstrap ALWAYS runs `pacman -Sy` internally, which needs
            # reachable mirrors.  In offline mode there is no network, so we
            # build a local file:// repo from the cached packages and point a
            # custom pacman.conf at it.  This makes `pacman -Sy` succeed by
            # "syncing" from the local repo DB.
            cache_dir = Path("/var/cache/pacman/pkg")
            pkg_files = sorted(cache_dir.glob("*.pkg.tar.zst"))
            if pkg_files:
                repo_db = cache_dir / "offline.db.tar.gz"
                log.info(
                    "Creating local repo DB from %d cached packages...",
                    len(pkg_files),
                )
                repo_add_cmd = [str(repo_db)] + [str(p) for p in pkg_files]
                result = subprocess.run(
                    ["repo-add"] + repo_add_cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    log.warning(
                        "repo-add failed (exit %d): %s",
                        result.returncode,
                        result.stderr,
                    )
                else:
                    log.info("Local repo DB created: %s", repo_db)
            # Custom pacman.conf that only uses the local offline repo.
            # SigLevel=Never is safe here — packages came from official repos
            # during ISO build and are stored in the trusted offline cache.
            offline_conf = Path("/tmp/offline-pacman.conf")
            offline_conf.write_text(
                "[options]\n"
                "Architecture = auto\n"
                "SigLevel = Never\n"
                "CacheDir = /var/cache/pacman/pkg\n"
                "\n"
                "[offline]\n"
                "Server = file:///var/cache/pacman/pkg\n"
            )
            log.info("Created offline pacman.conf at %s", offline_conf)
            cmd = ["pacstrap", "-c", "-C", str(offline_conf), target] + packages
        else:
            cmd = ["pacstrap", target] + packages
        max_retries = 10

        for attempt in range(1, max_retries + 1):
            self._update_progress(
                State.INSTALL,
                50,
                f"Ejecutando pacstrap (intento {attempt}/{max_retries})...",
            )

            log.info("Running pacstrap (attempt %d/%d): %s", attempt, max_retries, " ".join(cmd))
            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
            ) as proc:
                assert proc.stdout is not None
                for line in proc.stdout:
                    stripped = line.rstrip()
                    if stripped:
                        log.debug("[pacstrap] %s", stripped)
            returncode = proc.returncode

            if returncode == 0:
                log.info("pacstrap succeeded on attempt %d.", attempt)
                break

            log.warning(
                "pacstrap attempt %d/%d failed (exit %d). %s and retrying.",
                attempt, max_retries, returncode,
                "Regenerating mirrorlist" if not is_offline else "Offline — mirrorlist unchanged",
            )
            if not is_offline:
                self._generate_mirrorlist()

            if attempt == max_retries:
                raise InstallerError(
                    f"pacstrap failed after {max_retries} attempts (exit code {returncode}). "
                    "Check the install log for details."
                )
        else:
            raise InstallerError("pacstrap failed: unexpected loop exit.")

        # Regenerate fstab AFTER pacstrap — pacstrap overwrites /etc/fstab
        # with a generic one from the 'filesystem' package. We must restore
        # our custom Btrfs subvolume layout.
        self._regenerate_fstab()

        self._update_progress(State.INSTALL, 100, "Pacstrap completado")

    def _root_partition_device(self) -> str:
        """Return the root partition device path (e.g. /dev/vda2).

        Mirrors the logic of _root_device() in disk.sh:
        NVMe/mmcblk → p2 suffix, everything else → 2 suffix.
        """
        disk = self.config.disk.device
        if "nvme" in disk or "mmcblk" in disk:
            return f"{disk}p2"
        return f"{disk}2"

    def _root_device_for_fstab(self) -> str:
        """Return the device that holds the root filesystem.

        For LUKS installations this is /dev/mapper/ouroboros-root;
        otherwise it is the raw root partition.
        """
        if self.config.disk.use_luks:
            return "/dev/mapper/ouroboros-root"
        return self._root_partition_device()

    def _regenerate_fstab(self) -> None:
        target = self.config.install_target
        root_dev = self._root_device_for_fstab()

        log.info("Regenerating fstab after pacstrap (root_dev=%s)", root_dev)

        args = [
            "bash",
            str(OPS_DIR / "disk.sh"),
            "--action", "regenerate_fstab",
            "--target", target,
            "--root-device", root_dev,
        ]
        self._run_op(args, progress_title="Regenerating fstab", final_msg="fstab regenerated.")

    def _handle_configure(self) -> None:
        """CONFIGURE — chroot post-install configuration.

        No TUI prompts here anymore. Username/password are collected in
        the USER state before the disk is touched; desktop profile is
        collected in the DESKTOP state.
        """
        self._update_progress(State.CONFIGURE, 0, "Configurando sistema...")
        self._update_progress(State.CONFIGURE, 20, "Ejecutando configuración...")

        configure_script = OPS_DIR / "configure.sh"
        env = os.environ.copy()
        env.update(
            {
                "INSTALL_TARGET": self.config.install_target,
                "ROOT_DEVICE": self._root_device_for_fstab(),
                "LOCALE": self.config.locale.locale,
                "KEYMAP": self.config.locale.keymap,
                "TIMEZONE": self.config.locale.timezone,
                "HOSTNAME": self.config.network.hostname,
                "USERS_JSON": json.dumps([
                    {
                        "username": u.username,
                        "password_hash": u.password_hash,
                        "password": u.password_plaintext,
                        "groups": list(u.groups),
                        "shell": u.shell,
                        "real_name": u.real_name,
                        "homed_storage": u.homed_storage,
                        "tpm2_enroll": u.tpm2_enroll,
                        "fido2_enroll": u.fido2_enroll,
                    }
                    for u in self.config.users
                ]),
                # Backwards compat — configure.sh legacy functions use these
                "USERNAME": self.config.users[0].username if self.config.users else "",
                "USER_PASSWORD_HASH": self.config.users[0].password_hash if self.config.users else "",
                "USER_PASSWORD": self.config.users[0].password_plaintext if self.config.users else "",
                "USER_GROUPS": ",".join(self.config.users[0].groups) if self.config.users else "",
                "USER_SHELL": self.config.users[0].shell if self.config.users else "/bin/bash",
                "ENABLE_SSH": "1" if self.config.network.enable_ssh else "0",
                "ENABLE_IWD": "1" if self.config.network.enable_iwd else "0",
                "ENABLE_LUKS": "1" if self.config.disk.use_luks else "0",
                "ENABLE_TPM2": "1" if self.config.security.tpm2_unlock else "0",
                "LUKS_PARTITION": self._root_partition_device() if self.config.disk.use_luks else "",
                "DESKTOP_DM": dm_service(
                    resolve_dm(self.config.desktop.profile, self.config.desktop.dm)
                ) if resolve_dm(self.config.desktop.profile, self.config.desktop.dm) != "none" else "",
                "DESKTOP_PROFILE": self.config.desktop.profile,
                "DESKTOP_KDE_FLAVOR": self.config.desktop.kde_flavor,
                "GPU_DRIVER": self.config.desktop.gpu_driver,
                "DESKTOP_AUR_PACKAGES": " ".join(self.config.desktop.aur_packages),
                # F5: persist installer-chosen terminal + filemanager to firstboot
                "DESKTOP_PREFERRED_TERMINAL": self.config.desktop.preferred_terminal,
                "DESKTOP_PREFERRED_FILEMANAGER": self.config.desktop.preferred_filemanager,
                "HOMED_STORAGE": self.config.users[0].homed_storage if self.config.users else "subvolume",
                "WIFI_SSID": self.config.network.wifi_ssid,
                "WIFI_PASSPHRASE": self.config.network.wifi_passphrase,
                "BLUETOOTH_ENABLE": "1" if self.config.network.bluetooth_enable else "0",
                "FIDO2_PAM": "1" if self.config.security.fido2_pam else "0",
                "ENABLE_DUAL_BOOT": "1" if self.config.security.dual_boot else "0",
                "SECURE_BOOT": "1" if self.config.security.secure_boot else "0",
                "THUNDERBOLT_DETECTED": "1" if self.config.hardware.thunderbolt_detected else "0",
                "SBCTL_INCLUDE_MS_KEYS": "1" if self.config.security.sbctl_include_ms_keys else "0",
                "ROOT_PASSWORD": self.config.security.root_password,
                "ISO_VERSION": _read_iso_version(),
                "OFFLINE_MODE": "true" if (not self._has_internet() and self._detect_offline_cache()) else "false",
                "DOTS_PACK": self.config.dots_pack.pack or "",
                "DOTS_CHANNEL": self.config.dots_pack.channel,
            }
        )

        with subprocess.Popen(
            ["bash", str(configure_script)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        ) as _proc:
            assert _proc.stdout is not None
            for _line in _proc.stdout:
                stripped = _line.rstrip()
                if stripped:
                    log.debug("[configure] %s", stripped)
        result = _proc

        # Clear transient secrets after configure — no longer needed
        for u in self.config.users:
            u.password_plaintext = ""
        self.config.network.wifi_passphrase = ""
        self.config.security.root_password = ""

        if result.returncode != 0:
            raise InstallerError(
                f"System configuration failed (exit {result.returncode}). "
                "See /tmp/ouroborOS-install.log"
            )

        self._update_progress(State.CONFIGURE, 100, "Configuración completada")

    def _handle_snapshot(self) -> None:
        """SNAPSHOT — create baseline Btrfs snapshot."""
        self._update_progress(State.SNAPSHOT, 0, "Creando snapshot...")

        with subprocess.Popen(
            [
                "bash",
                str(OPS_DIR / "snapshot.sh"),
                "--action", "create_install_snapshot",
                "--target", self.config.install_target,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        ) as _snap_proc:
            assert _snap_proc.stdout is not None
            for _line in _snap_proc.stdout:
                stripped = _line.rstrip()
                if stripped:
                    log.debug("[snapshot] %s", stripped)
        result = _snap_proc
        if result.returncode != 0:
            log.warning("Snapshot creation failed — continuing without snapshot.")
        else:
            log.info("Installation snapshot created.")

        # Make @ truly read-only at the Btrfs level (not just mount-option ro).
        # Btrfs superblock sharing: when @var/@etc/@home are mounted rw from the
        # same device, the mount-option ro on @ is overridden at the kernel level.
        # btrfs property set ro=true enforces immutability at the subvolume level
        # regardless of the device's overall rw state.
        ro_result = subprocess.run(
            ["btrfs", "property", "set", self.config.install_target, "ro", "true"],
            check=False,
        )
        if ro_result.returncode != 0:
            log.warning("Could not set Btrfs ro property on root subvolume — root may not be immutable.")
        else:
            log.info("Root subvolume (@) set read-only via Btrfs property.")

        self._update_progress(State.SNAPSHOT, 100, "Snapshot creado")

    def _write_system_yaml(self) -> None:
        """Write /etc/ouroboros/system.yaml to the installed target."""
        import yaml  # noqa: PLC0415

        target = Path(self.config.install_target)
        ouroboros_dir = target / "etc" / "ouroboros"
        ouroboros_dir.mkdir(parents=True, exist_ok=True)

        system_yaml_path = ouroboros_dir / "system.yaml"
        data = self.config.to_system_yaml()
        system_yaml_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        system_yaml_path.chmod(0o644)
        log.info("system.yaml written: %s", system_yaml_path)

    def _write_install_snapshot_metadata(self) -> None:
        """Write .snapshot.yaml inside the install snapshot after system.yaml exists."""
        import hashlib  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        snap_dir = Path(self.config.install_target) / ".snapshots" / "install"
        if not snap_dir.exists():
            log.debug("Install snapshot dir not found — skipping .snapshot.yaml")
            return

        system_yaml = Path(self.config.install_target) / "etc" / "ouroboros" / "system.yaml"
        if system_yaml.exists():
            raw = system_yaml.read_bytes()
            sys_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
            version = self.config.to_system_yaml()["version"]
            pkg_count = len(self.config.installed_packages)
        else:
            sys_hash = "none"
            version = "unknown"
            pkg_count = 0

        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = (
            f"snapshot: install\n"
            f"created: {created}\n"
            f"type: install\n"
            f"system_version: {version}\n"
            f"system_yaml_hash: {sys_hash}\n"
            f"packages_count: {pkg_count}\n"
        )
        snap_yaml = snap_dir / ".snapshot.yaml"
        import subprocess  # noqa: PLC0415
        subprocess.run(["btrfs", "property", "set", str(snap_dir), "ro", "false"], check=True)
        try:
            snap_yaml.write_text(metadata, encoding="utf-8")
        finally:
            subprocess.run(["btrfs", "property", "set", str(snap_dir), "ro", "true"], check=True)
        log.info("Install snapshot metadata written: %s", snap_yaml)

    def _handle_finish(self) -> None:
        """FINISH — write system.yaml, show summary, then reboot or shutdown."""
        self._write_system_yaml()
        self._write_install_snapshot_metadata()

        if self.tui:
            self.tui.finish_install_progress()
            self.tui.show_summary(self.config)
            action = self.tui.show_post_install_action()
        else:
            action = self.config.post_install_action

        log.info("Installation complete. System ready.")

        if action == "shutdown":
            log.info("Shutting down system...")
            os.system("poweroff")
        elif action == "none":
            log.info("Post-install action: none. Staying up.")
        else:
            log.info("Rebooting system...")
            os.system("reboot")

    # --- Preflight check helpers --------------------------------------------

    def _check_uefi(self) -> None:
        if not Path("/sys/firmware/efi").exists():
            raise InstallerError(
                "UEFI mode not detected. ouroborOS requires UEFI boot."
            )

    def _check_root(self) -> None:
        if os.geteuid() != 0:
            raise InstallerError("Installer must be run as root.")

    def _check_tools(self) -> None:
        required = [
            "sgdisk", "mkfs.btrfs", "mkfs.fat", "pacstrap", "arch-chroot", "genfstab",
        ]
        missing = [t for t in required if not self._which(t)]
        if missing:
            raise InstallerError(f"Missing required tools: {', '.join(missing)}")

    def _check_ram(self) -> None:
        mem_kb = 0
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    mem_kb = int(line.split()[1])
                    break
        except OSError:
            pass
        if mem_kb < 1_024_000:
            raise InstallerError(
                f"Insufficient RAM: {mem_kb // 1024} MiB detected, 1024 MiB required."
            )

    def _check_network(self) -> None:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise InstallerError(
                "No internet connectivity. Connect to a network before installing."
            )

    # --- Utility ------------------------------------------------------------

    @staticmethod
    def _which(tool: str) -> bool:
        """Return True if tool is available in PATH."""
        import shutil
        return shutil.which(tool) is not None

    def _run_op(
        self,
        args: list[str],
        progress_title: str = "",
        final_msg: str = "",
    ) -> None:
        """Run a shell command, streaming output to the log file."""
        log.debug("Running: %s", " ".join(args))
        with subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        ) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                log.debug("[op] %s", line.rstrip())

        if proc.returncode != 0:
            raise InstallerError(
                f"Operation failed (exit {proc.returncode}): {' '.join(args)}"
            )
        if final_msg:
            log.info(final_msg)
