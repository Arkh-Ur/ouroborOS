"""state_machine.py — ouroborOS installer finite state machine.

The installer is modelled as a linear FSM with checkpointing.
Each state corresponds to one installation phase. If the installer
is interrupted, it can resume from the last completed checkpoint.

State flow:
    INIT → PREFLIGHT → LOCALE → PARTITION → FORMAT → INSTALL
         → CONFIGURE → SNAPSHOT → FINISH

Error states:
    Any state can transition to ERROR_RECOVERABLE (retry) or FATAL (abort).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

from installer.config import InstallerConfig, find_unattended_config, load_config
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

# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class State(Enum):
    """All states of the ouroborOS installer FSM."""

    INIT = auto()
    PREFLIGHT = auto()
    LOCALE = auto()
    PARTITION = auto()
    FORMAT = auto()
    INSTALL = auto()
    CONFIGURE = auto()
    SNAPSHOT = auto()
    FINISH = auto()
    ERROR_RECOVERABLE = auto()
    FATAL = auto()


# State execution order (excludes error states)
_STATE_ORDER: list[State] = [
    State.INIT,
    State.PREFLIGHT,
    State.LOCALE,
    State.PARTITION,
    State.FORMAT,
    State.INSTALL,
    State.CONFIGURE,
    State.SNAPSHOT,
    State.FINISH,
]

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


def _load_config_checkpoint() -> Optional[InstallerConfig]:
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

    def __init__(self, resume: bool = False, config_path: Optional[Path] = None) -> None:
        self.state: State = State.INIT
        self.config: InstallerConfig = InstallerConfig()
        self.tui: Optional[TUI] = None
        self._resume = resume
        self._config_path = config_path
        self._handler_map: dict[State, Callable[[], None]] = {
            State.INIT: self._handle_init,
            State.PREFLIGHT: self._handle_preflight,
            State.LOCALE: self._handle_locale,
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
                                raise FatalError(f"User aborted at state {state.name}.") from exc
                        else:
                            log.error("Unattended mode: aborting on error.")
                            raise FatalError(str(exc)) from exc

        except FatalError as exc:
            self.state = State.FATAL
            log.critical("Fatal error: %s", exc)
            if self.tui:
                self.tui.show_error(str(exc), recoverable=False)
            return 1
        except KeyboardInterrupt:
            self.state = State.FATAL
            log.warning("Installation interrupted by user.")
            if self.tui:
                self.tui.show_error("Installation cancelled by user.", recoverable=False)
            return 1

        return 0

    # --- State handlers -----------------------------------------------------

    def _handle_init(self) -> None:
        """INIT — detect unattended mode or initialise TUI."""
        # Check for unattended config
        config_path = self._config_path or find_unattended_config()
        if config_path:
            log.info("Unattended config found: %s", config_path)
            self.config = load_config(config_path)
            self.tui = None
        else:
            self.tui = TUI(title="ouroborOS Installer")
            self.tui.show_welcome()

    def _handle_preflight(self) -> None:
        """PREFLIGHT — verify system requirements."""
        checks = [
            ("UEFI mode", self._check_uefi),
            ("Root privileges", self._check_root),
            ("Required tools", self._check_tools),
            ("Minimum RAM (1 GiB)", self._check_ram),
            ("Internet connectivity", self._check_network),
        ]

        if self.tui:
            self.tui.show_progress("Preflight Checks", "Verifying system requirements...", 0)

        failed = []
        for i, (name, check_fn) in enumerate(checks):
            try:
                check_fn()
                log.info("Preflight check passed: %s", name)
            except InstallerError as exc:
                log.warning("Preflight check failed: %s — %s", name, exc)
                failed.append(f"{name}: {exc}")
            if self.tui:
                pct = int((i + 1) / len(checks) * 100)
                self.tui.show_progress("Preflight Checks", f"Checking: {name}", pct)

        if failed:
            raise InstallerError("Preflight checks failed:\n" + "\n".join(failed))

    def _handle_locale(self) -> None:
        """LOCALE — set locale, timezone, keymap."""
        if self.tui:
            locale_cfg = self.tui.show_locale_menu()
            self.config.locale.locale = locale_cfg["locale"]
            self.config.locale.keymap = locale_cfg["keymap"]
            self.config.locale.timezone = locale_cfg["timezone"]
            self.config.network.hostname = self.tui.show_hostname_input()
        log.info(
            "Locale: %s / %s / %s",
            self.config.locale.locale,
            self.config.locale.keymap,
            self.config.locale.timezone,
        )

    def _handle_partition(self) -> None:
        """PARTITION — disk selection, layout preview, confirmation."""
        if self.tui:
            disk = self.tui.show_disk_selection()
            self.config.disk.device = disk
            use_luks = self.tui.show_luks_prompt()
            self.config.disk.use_luks = use_luks
            if use_luks:
                self.config.disk.luks_passphrase = self.tui.show_passphrase_input()
            self.tui.show_partition_preview(disk, use_luks)
            confirmed = self.tui.show_confirmation(
                "WARNING: All data on {} will be destroyed. Continue?".format(disk)
            )
            if not confirmed:
                raise InstallerError("User did not confirm disk wipe. Aborting.")
        log.info("Target disk: %s (LUKS: %s)", self.config.disk.device, self.config.disk.use_luks)

    def _handle_format(self) -> None:
        """FORMAT — partition, format, create subvolumes, mount, fstab."""
        if self.tui:
            self.tui.show_progress("Disk Setup", "Preparing disk...", 0)

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

        # Clear passphrase from memory immediately after use
        self.config.disk.luks_passphrase = ""

    def _handle_install(self) -> None:
        """INSTALL — pacstrap base system."""
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
        ] + self.config.extra_packages

        if self.tui:
            self.tui.show_progress("Installing Base System", "Running pacstrap...", 0)

        cmd = ["pacstrap", "-K", self.config.install_target] + packages
        log.info("Running pacstrap: %s", " ".join(cmd))

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            raise InstallerError(
                f"pacstrap failed with exit code {result.returncode}. "
                "Check the install log for details."
            )

        if self.tui:
            self.tui.show_progress("Installing Base System", "pacstrap complete.", 100)

    def _handle_configure(self) -> None:
        """CONFIGURE — chroot post-install configuration."""
        if self.tui:
            user_cfg = self.tui.show_user_creation()
            self.config.user.username = user_cfg["username"]
            self.config.user.password_hash = user_cfg["password_hash"]

        if self.tui:
            self.tui.show_progress("System Configuration", "Configuring installed system...", 0)

        configure_script = OPS_DIR / "configure.sh"
        env = os.environ.copy()
        env.update(
            {
                "INSTALL_TARGET": self.config.install_target,
                "LOCALE": self.config.locale.locale,
                "KEYMAP": self.config.locale.keymap,
                "TIMEZONE": self.config.locale.timezone,
                "HOSTNAME": self.config.network.hostname,
                "USERNAME": self.config.user.username,
                "USER_PASSWORD_HASH": self.config.user.password_hash,
                "USER_GROUPS": ",".join(self.config.user.groups),
                "USER_SHELL": self.config.user.shell,
                "ENABLE_IWD": "1" if self.config.network.enable_iwd else "0",
                "ENABLE_LUKS": "1" if self.config.disk.use_luks else "0",
            }
        )

        result = subprocess.run(["bash", str(configure_script)], env=env, check=False)
        if result.returncode != 0:
            raise InstallerError(
                f"System configuration failed (exit {result.returncode}). "
                "See /tmp/ouroborOS-install.log"
            )

        if self.tui:
            self.tui.show_progress("System Configuration", "Configuration complete.", 100)

    def _handle_snapshot(self) -> None:
        """SNAPSHOT — create baseline Btrfs snapshot."""
        if self.tui:
            self.tui.show_progress("Creating Snapshot", "Snapshotting install baseline...", 0)

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
            # Non-fatal: snapshot failure should not abort the install
            log.warning("Snapshot creation failed — continuing without snapshot.")
        else:
            log.info("Installation snapshot created.")

    def _handle_finish(self) -> None:
        """FINISH — show completion summary and prompt for reboot."""
        if self.tui:
            self.tui.show_summary(self.config)

        log.info("Installation complete. System ready.")

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
        required = ["sgdisk", "mkfs.btrfs", "mkfs.fat", "pacstrap", "arch-chroot", "genfstab"]
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
        return subprocess.run(
            ["which", tool], capture_output=True, check=False
        ).returncode == 0

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
