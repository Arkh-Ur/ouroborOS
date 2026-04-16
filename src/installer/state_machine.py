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
from installer.tui import TUI

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
    State.SECURE_BOOT: (21, 23),
    State.PARTITION: (23, 30),
    State.FORMAT: (30, 45),
    State.INSTALL: (45, 70),
    State.CONFIGURE: (70, 90),
    State.SNAPSHOT: (90, 95),
    State.FINISH: (95, 100),
}

_STEP_LABELS: dict[State, str] = {
    State.INIT: "Iniciando",
    State.NETWORK_SETUP: "Conectando a la red",
    State.PREFLIGHT: "Verificando requisitos",
    State.LOCALE: "Configurando idioma",
    State.USER: "Creando usuario",
    State.DESKTOP: "Seleccionando escritorio",
    State.SECURE_BOOT: "Configurando Secure Boot",
    State.PARTITION: "Seleccionando disco",
    State.FORMAT: "Preparando disco",
    State.INSTALL: "Instalando paquetes",
    State.CONFIGURE: "Configurando sistema",
    State.SNAPSHOT: "Creando snapshot",
    State.FINISH: "Finalizando",
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
        label = _STEP_LABELS.get(state, state.name)
        if self.tui:
            self.tui.update_install_progress(global_pct, step_num, total, label, detail)

    def _handle_init(self) -> None:
        """INIT — detect unattended mode or initialise TUI."""
        config_path = self._config_path or find_unattended_config()
        if config_path:
            log.info("Unattended config found: %s", config_path)
            self.config = load_config(config_path)
            self.tui = None
            return

        # No config found — start interactive TUI
        self.tui = TUI(title="ouroborOS Installer")
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
        checks = [
            ("UEFI mode", self._check_uefi),
            ("Root privileges", self._check_root),
            ("Required tools", self._check_tools),
            ("Minimum RAM (1 GiB)", self._check_ram),
            ("Internet connectivity", self._check_network),
        ]

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
        """USER — collect username, password, and shell BEFORE touching the disk.

        This state used to live inside CONFIGURE (after pacstrap). It was
        moved forward so a cancelled prompt cannot waste a disk wipe.
        """
        self._update_progress(State.USER, 0)
        if self.tui:
            user_cfg = self.tui.show_user_creation()
            self.config.user.username = user_cfg["username"]
            self.config.user.password_hash = user_cfg["password_hash"]
            if "password" in user_cfg:
                self.config.user.password_plaintext = user_cfg["password"]

            shell_name = self.tui.show_shell_selection()
            self.config.user.shell = shell_path(shell_name)

            # If the chosen shell is not part of 'base', schedule it for install
            pkg = shell_package(shell_name)
            if pkg and pkg not in self.config.extra_packages:
                self.config.extra_packages.append(pkg)
                log.info("Shell package queued: %s", pkg)

        log.info(
            "User configured: %s (shell: %s)",
            self.config.user.username,
            self.config.user.shell,
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

    def _handle_secure_boot(self) -> None:
        """SECURE_BOOT — show Secure Boot setup instructions if enabled in config."""
        self._update_progress(State.SECURE_BOOT, 0)
        if not self.config.security.secure_boot:
            log.info("Secure Boot disabled in config — skipping state.")
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

        Strategy: broad pool → score → keep fastest 10.
        1. Get the 50 most-recently-synced mirrors (age <= 24h).
        2. Sort by MirrorStatus score (composite: delay + completion + speed).
        3. Keep the fastest 10.
        4. If that fails (e.g. geoip unavailable), fallback to worldwide with
           the same filters.
        """
        host_mirrorlist = Path("/etc/pacman.d/mirrorlist")
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

        pacstrap -K copies the host keyring into the new root, but the
        live ISO keyring may not be populated yet.  Run init + populate
        once so that subsequent pacstrap calls can verify signatures.
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

    def _handle_install(self) -> None:
        """INSTALL — pacstrap base system with automatic retries."""
        target = self.config.install_target
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
            "openssh",
            "which",
            # systemd-nspawn + machinectl ship with the `systemd` package
            # (already in base), used by `our-container` for container workflows.
        ] + self.config.extra_packages + packages_for(
            self.config.desktop.profile,
            kde_flavor=self.config.desktop.kde_flavor,
        )

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

        cmd = ["pacstrap", "-K", target] + packages
        max_retries = 10

        for attempt in range(1, max_retries + 1):
            self._update_progress(
                State.INSTALL,
                50,
                f"Ejecutando pacstrap (intento {attempt}/{max_retries})...",
            )

            log.info("Running pacstrap (attempt %d/%d): %s", attempt, max_retries, " ".join(cmd))
            result = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Always log pacstrap output — package hooks may emit warnings
            # (e.g. filesystem .install "error: command failed to execute correctly")
            # that are non-fatal but important for diagnostics.
            if result.stdout:
                for line in result.stdout.splitlines():
                    stripped = line.strip()
                    if stripped:
                        log.debug("[pacstrap] %s", stripped)

            if result.returncode == 0:
                log.info("pacstrap succeeded on attempt %d.", attempt)
                break

            log.warning(
                "pacstrap attempt %d/%d failed (exit %d). Regenerating mirrorlist and retrying.",
                attempt, max_retries, result.returncode,
            )
            self._generate_mirrorlist()

            if attempt == max_retries:
                raise InstallerError(
                    f"pacstrap failed after {max_retries} attempts (exit code {result.returncode}). "
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
                "USERNAME": self.config.user.username,
                "USER_PASSWORD_HASH": self.config.user.password_hash,
                "USER_PASSWORD": self.config.user.password_plaintext,
                "USER_GROUPS": ",".join(self.config.user.groups),
                "USER_SHELL": self.config.user.shell,
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
                "HOMED_STORAGE": self.config.user.homed_storage,
                "WIFI_SSID": self.config.network.wifi_ssid,
                "WIFI_PASSPHRASE": self.config.network.wifi_passphrase,
                "BLUETOOTH_ENABLE": "1" if self.config.network.bluetooth_enable else "0",
                "FIDO2_PAM": "1" if self.config.security.fido2_pam else "0",
                "ISO_VERSION": _read_iso_version(),
            }
        )

        result = subprocess.run(["bash", str(configure_script)], env=env, check=False)

        # Clear transient secrets after configure — no longer needed
        self.config.user.password_plaintext = ""
        self.config.network.wifi_passphrase = ""

        if result.returncode != 0:
            raise InstallerError(
                f"System configuration failed (exit {result.returncode}). "
                "See /tmp/ouroborOS-install.log"
            )

        self._update_progress(State.CONFIGURE, 100, "Configuración completada")

    def _handle_snapshot(self) -> None:
        """SNAPSHOT — create baseline Btrfs snapshot."""
        self._update_progress(State.SNAPSHOT, 0, "Creando snapshot...")

        result = subprocess.run(
            [
                "bash",
                str(OPS_DIR / "snapshot.sh"),
                "--action", "create_install_snapshot",
                "--target", self.config.install_target,
            ],
            check=False,
        )
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

    def _handle_finish(self) -> None:
        """FINISH — show completion summary, then reboot or shutdown."""
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
