"""tui.py — ouroborOS installer TUI layer.

Primary backend: rich (Python library). Fallback: whiptail (shell dialog).
All TUI functions return structured data; they never modify global state.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
    from rich.text import Text

    HAS_RICH = True
except ImportError:
    Console = None  # type: ignore[assignment,misc]
    Panel = None  # type: ignore[assignment,misc]
    Confirm = None  # type: ignore[assignment,misc]
    IntPrompt = None  # type: ignore[assignment,misc]
    Prompt = None  # type: ignore[assignment,misc]
    Table = None  # type: ignore[assignment,misc]
    Text = None  # type: ignore[assignment,misc]
    HAS_RICH = False


class TUIError(Exception):
    """Raised when a TUI operation fails."""


def _get_whiptail_path() -> str:
    path = shutil.which("whiptail")
    if path is None:
        raise TUIError("whiptail not installed. Install 'libnewt' package.")
    return path


def _whiptail(*args: str, input_text: str | None = None) -> tuple[int, str]:
    cmd = [_get_whiptail_path()] + list(args)
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stderr.strip()


def _lsblk_disks() -> list[dict[str, str]]:
    result = subprocess.run(
        ["lsblk", "--json", "--output", "NAME,SIZE,MODEL,TYPE,HOTPLUG"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        disks = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") == "disk":
                disks.append(
                    {
                        "name": f"/dev/{dev['name']}",
                        "size": dev.get("size", "?"),
                        "model": dev.get("model") or "Unknown",
                    }
                )
        return disks
    except (json.JSONDecodeError, KeyError):
        return []


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()[:16]
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-salt", salt, password],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TUI:
    """ouroborOS installer TUI controller.

    Uses rich as primary backend with whiptail as automatic fallback.
    All show_* methods return structured data and never modify global state.
    """

    _HEIGHT = 20
    _WIDTH = 72

    def __init__(self, title: str = "ouroborOS Installer") -> None:
        self._title = title
        self._progress_title: str = ""
        self._install_progress_active: bool = False
        self._install_progress_pct: int = 0

        if HAS_RICH:
            self._backend = "rich"
            self._console: Console | None = Console(force_terminal=True)
        else:
            self._backend = "whiptail"
            self._console = None
            self._check_whiptail()

    def _check_whiptail(self) -> None:
        if shutil.which("whiptail") is None:
            raise TUIError(
                "Neither rich nor whiptail available. "
                "Install 'python-rich' or 'libnewt'."
            )

    def _args(self, *extra: str) -> list[str]:
        return ["--title", self._title] + list(extra)

    def _stop_progress(self) -> None:
        if self._progress_title or self._install_progress_active:
            import sys
            sys.stdout.write("\r" + " " * 120 + "\r")
            sys.stdout.flush()
            self._progress_title = ""
            self._install_progress_active = False

    # ------------------------------------------------------------------
    # Welcome
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
        if self._backend == "rich":
            self._rich_welcome()
        else:
            self._whiptail_welcome()

    def _rich_welcome(self) -> None:
        assert self._console is not None
        self._stop_progress()
        self._console.print()
        self._console.print(
            Panel(
                Text.from_markup(
                    "\n[bold cyan]Welcome to the ouroborOS installer.[/]\n\n"
                    "ouroborOS is an ArchLinux-based distribution with an immutable\n"
                    "Btrfs root filesystem and a fully systemd-native stack.\n\n"
                    "This installer will guide you through "
                    "the installation process.\n\n"
                    "[bold red]WARNING: This will ERASE "
                    "the target disk completely.[/]\n"
                ),
                title="[bold cyan]ouroborOS Installer[/]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        info = Table(show_header=False, box=None, padding=(0, 2))
        info.add_column(style="dim")
        info.add_column(style="bold")
        info.add_row("System", "ArchLinux-based")
        info.add_row("Filesystem", "Btrfs (immutable root)")
        info.add_row("Bootloader", "systemd-boot")
        info.add_row("Network", "systemd-networkd + iwd")
        self._console.print(info)
        self._countdown(30)

    def _countdown(self, seconds: int) -> None:
        """Show a countdown that auto-continues after *seconds*.

        Pressing Enter early skips the wait.
        """
        import select
        import sys

        assert self._console is not None

        if not sys.stdin.isatty():
            return

        for remaining in range(seconds, 0, -1):
            sys.stdout.write(
                f"\r  [dim]Continuing in {remaining}s... "
                f"(Enter to skip)[/]\033[K"
            )
            sys.stdout.flush()
            dr, _, _ = select.select([sys.stdin], [], [], 1.0)
            if dr:
                sys.stdin.readline()
                break
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _whiptail_welcome(self) -> None:
        text = (
            "Welcome to the ouroborOS installer.\n\n"
            "ouroborOS is an ArchLinux-based distribution with an immutable\n"
            "Btrfs root filesystem and a fully systemd-native stack.\n\n"
            "This installer will guide you through the installation process.\n\n"
            "WARNING: This will ERASE the target disk completely."
        )
        _whiptail(
            *self._args(
                "--msgbox",
                text,
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def show_progress(self, title: str, text: str, percent: int) -> None:
        if self._backend == "rich":
            self._rich_progress(title, text, percent)
        else:
            self._whiptail_progress(title, text, percent)

    def _rich_progress(self, title: str, text: str, percent: int) -> None:
        assert self._console is not None
        pct = max(0, min(100, percent))
        self._progress_title = title

        filled = int(pct / 100 * 40)
        bar = "█" * filled + "░" * (40 - filled)
        self._console.print(
            f"\r  [bold cyan]{title}[/] |{bar}| {pct:>3}% — {text}"
            + " " * 10,
            end="",
            highlight=False,
        )
        if pct >= 100:
            self._console.print()
            self._progress_title = ""

    def _whiptail_progress(self, title: str, text: str, percent: int) -> None:
        subprocess.run(
            [
                _get_whiptail_path(),
                "--title",
                title,
                "--gauge",
                text,
                str(self._HEIGHT),
                str(self._WIDTH),
                str(max(0, min(100, percent))),
            ],
            input="",
            capture_output=True,
            text=True,
            check=False,
        )

    # ------------------------------------------------------------------
    # Global Install Progress
    # ------------------------------------------------------------------

    def start_install_progress(self) -> None:
        """Start the global installation progress bar."""
        self._install_progress_active = True
        self._install_progress_pct = 0

    def update_install_progress(
        self,
        percent: int,
        step_num: int,
        total_steps: int,
        step_label: str,
        detail: str = "",
    ) -> None:
        """Update the global installation progress bar.

        Args:
            percent: Overall progress 0-100.
            step_num: Current step number (1-based).
            total_steps: Total number of steps.
            step_label: Human-readable step name.
            detail: Optional detail text for the current sub-task.
        """
        self._install_progress_active = True
        pct = max(0, min(100, percent))
        self._install_progress_pct = pct
        step_text = f"Paso {step_num}/{total_steps}: {step_label}"
        if detail:
            step_text += f" — {detail}"
        self._update_install_bar(pct, step_text)

    def stop_install_progress(self) -> None:
        """Clear the progress bar (for interactive prompts)."""
        if self._install_progress_active:
            import sys
            sys.stdout.write("\r" + " " * 120 + "\r")
            sys.stdout.flush()
            self._install_progress_active = False

    def finish_install_progress(self) -> None:
        """Mark the global progress as complete (100%)."""
        self._install_progress_pct = 100
        self._update_install_bar(100, "Instalación completa")
        self._install_progress_active = False

    def _update_install_bar(self, pct: int, step_text: str) -> None:
        """Render the progress bar to stdout."""
        import sys
        filled = int(pct / 100 * 40)
        bar = "█" * filled + "░" * (40 - filled)
        line = f"\r  |{bar}| {pct:>3}%  {step_text}" + " " * 20
        sys.stdout.write(line)
        sys.stdout.flush()
        if pct >= 100:
            sys.stdout.write("\n")
            sys.stdout.flush()

    # ------------------------------------------------------------------
    # Locale
    # ------------------------------------------------------------------

    _LOCALE_OPTIONS: list[tuple[str, str]] = [
        ("en_US.UTF-8", "English (US) - UTF-8"),
        ("en_GB.UTF-8", "English (UK) - UTF-8"),
        ("es_ES.UTF-8", "Spanish (Spain) - UTF-8"),
        ("es_MX.UTF-8", "Spanish (Mexico) - UTF-8"),
        ("fr_FR.UTF-8", "French (France) - UTF-8"),
        ("de_DE.UTF-8", "German (Germany) - UTF-8"),
        ("pt_BR.UTF-8", "Portuguese (Brazil) - UTF-8"),
        ("ja_JP.UTF-8", "Japanese - UTF-8"),
        ("zh_CN.UTF-8", "Chinese Simplified - UTF-8"),
    ]

    _KEYMAP_OPTIONS: list[tuple[str, str]] = [
        ("us", "US QWERTY"),
        ("gb", "UK QWERTY"),
        ("es", "Spanish"),
        ("fr", "French AZERTY"),
        ("de", "German QWERTZ"),
        ("latam", "Latin American"),
        ("br-abnt2", "Brazilian ABNT2"),
        ("jp106", "Japanese 106-key"),
        ("dvorak", "US Dvorak"),
        ("colemak", "Colemak"),
    ]

    def show_locale_menu(self) -> dict[str, str]:
        if self._backend == "rich":
            return self._rich_locale_menu()
        return self._whiptail_locale_menu()

    def _rich_locale_menu(self) -> dict[str, str]:
        locale = self._rich_select(
            "Locale", "Select system locale:", self._LOCALE_OPTIONS,
            default="en_US.UTF-8",
        )
        keymap = self._rich_select(
            "Keyboard Layout", "Select keyboard layout:", self._KEYMAP_OPTIONS,
            default="us",
        )
        timezone = self._rich_input(
            "Timezone",
            "Enter timezone (e.g. America/New_York, Europe/Madrid, UTC)",
            default="UTC",
        )
        return {"locale": locale, "keymap": keymap, "timezone": timezone}

    def _whiptail_locale_menu(self) -> dict[str, str]:
        locale = self._select_from_list(
            "Locale", "Select system locale:", self._LOCALE_OPTIONS,
            default="en_US.UTF-8",
        )
        keymap = self._select_from_list(
            "Keyboard Layout", "Select keyboard layout:", self._KEYMAP_OPTIONS,
            default="us",
        )
        timezone = self._input_box(
            "Timezone",
            "Enter timezone (e.g. America/New_York, Europe/Madrid, UTC):",
            default="UTC",
        )
        return {"locale": locale, "keymap": keymap, "timezone": timezone}

    # ------------------------------------------------------------------
    # Hostname
    # ------------------------------------------------------------------

    def show_hostname_input(self) -> str:
        if self._backend == "rich":
            return self._rich_input(
                "Hostname",
                "Enter a hostname for the installed system",
                default="ouroboros",
            )
        return self._input_box(
            "Hostname",
            "Enter a hostname for the installed system:",
            default="ouroboros",
        )

    # ------------------------------------------------------------------
    # Desktop profile selection
    # ------------------------------------------------------------------

    _DESKTOP_PROFILES: list[tuple[str, str]] = [
        ("minimal",  "Nothing extra — TTY-only base (you install the DE yourself)"),
        ("hyprland", "Hyprland + Hypr ecosystem (waybar, foot, hyprlauncher, hyprlock…)"),
        ("niri",     "Niri + foot + fuzzel (scrollable-tiling Wayland)"),
        ("gnome",    "GNOME desktop (gdm by default)"),
        ("kde",      "KDE Plasma — flavor selector next (plm by default)"),
        ("cosmic",   "COSMIC Desktop by System76 — Wayland-native, greetd"),
    ]

    def show_desktop_selection(self) -> str:
        """Prompt for a desktop profile. Returns the profile name."""
        if self._backend == "rich":
            return self._rich_select(
                "Desktop Profile",
                "Select a desktop profile for the installed system:",
                self._DESKTOP_PROFILES,
                default="minimal",
            )
        return self._select_from_list(
            "Desktop Profile",
            "Select a desktop profile for the installed system:",
            self._DESKTOP_PROFILES,
            default="minimal",
        )

    # ------------------------------------------------------------------
    # Display manager selection
    # ------------------------------------------------------------------

    _DM_OPTIONS: list[tuple[str, str]] = [
        ("auto",   "Recommended for this profile (default)"),
        ("gdm",    "GNOME Display Manager — Wayland-native"),
        ("sddm",   "Simple Desktop Display Manager — Wayland support"),
        ("plm",    "Plasma Login Manager — KDE native, fork of SDDM"),
        ("greetd", "greetd — generic greeter daemon (COSMIC uses cosmic-greeter)"),
        ("none",   "TTY login — launch your session manually"),
    ]

    def show_dm_selection(self, profile: str = "") -> str:
        """Prompt for a display manager. Returns 'auto', 'gdm', 'sddm', 'greetd', or 'none'."""
        label = f"Display Manager (profile: {profile})" if profile else "Display Manager"
        prompt = "Select a display manager:"
        if self._backend == "rich":
            return self._rich_select(label, prompt, self._DM_OPTIONS, default="auto")
        return self._select_from_list(label, prompt, self._DM_OPTIONS, default="auto")

    # ------------------------------------------------------------------
    # KDE flavor selection
    # ------------------------------------------------------------------

    _KDE_FLAVOR_OPTIONS: list[tuple[str, str]] = [
        ("plasma-meta",    "plasma-meta    — curated set, recommended (~1 GB)"),
        ("plasma",         "plasma         — full group, all components (~1.5 GB)"),
        ("plasma-desktop", "plasma-desktop — minimal shell only (~400 MB)"),
    ]

    def show_kde_flavor(self) -> str:
        """Prompt for a KDE Plasma flavor. Returns 'plasma-meta', 'plasma', or 'plasma-desktop'."""
        if self._backend == "rich":
            return self._rich_select(
                "KDE Plasma Flavor",
                "Select which Plasma meta-package to install:",
                self._KDE_FLAVOR_OPTIONS,
                default="plasma-meta",
            )
        return self._select_from_list(
            "KDE Plasma Flavor",
            "Select which Plasma meta-package to install:",
            self._KDE_FLAVOR_OPTIONS,
            default="plasma-meta",
        )

    # ------------------------------------------------------------------
    # GPU driver selection
    # ------------------------------------------------------------------

    _GPU_OPTIONS: list[tuple[str, str]] = [
        ("auto",         "Auto-detect GPU and install recommended driver (default)"),
        ("mesa",         "Mesa — Intel / AMD open source (xf86-video-amdgpu + vulkan-radeon)"),
        ("amdgpu",       "AMD GPU — mesa + vulkan-radeon explicitly"),
        ("nvidia",       "NVIDIA — proprietary driver (recommended for NVIDIA hardware)"),
        ("nvidia-open",  "NVIDIA Open — open kernel module (Turing/Ampere+)"),
        ("none",         "Skip — install GPU drivers manually after reboot"),
    ]

    def show_gpu_selection(self, detected: str = "auto") -> str:
        """Prompt for GPU driver choice. *detected* is shown as the auto-detect result."""
        label = "GPU Driver"
        prompt = (
            f"Detected GPU family: {detected}. Select the driver to install:"
            if detected != "auto"
            else "Select the GPU driver to install:"
        )
        if self._backend == "rich":
            return self._rich_select(label, prompt, self._GPU_OPTIONS, default="auto")
        return self._select_from_list(label, prompt, self._GPU_OPTIONS, default="auto")

    # ------------------------------------------------------------------
    # Shell selection
    # ------------------------------------------------------------------

    _SHELL_OPTIONS: list[tuple[str, str]] = [
        ("bash", "Bash   — POSIX-compatible, universal default (recommended)"),
        ("zsh",  "Zsh    — Bash-compatible with advanced completion and prompts"),
        ("fish", "Fish   — Modern and user-friendly (non-POSIX, breaks legacy scripts)"),
    ]

    def show_shell_selection(self) -> str:
        """Prompt for a login shell. Returns the shell name ('bash', 'zsh', 'fish')."""
        if self._backend == "rich":
            return self._rich_select(
                "Login Shell",
                "Select the login shell for your user account:",
                self._SHELL_OPTIONS,
                default="bash",
            )
        return self._select_from_list(
            "Login Shell",
            "Select the login shell for your user account:",
            self._SHELL_OPTIONS,
            default="bash",
        )

    # ------------------------------------------------------------------
    # Disk selection
    # ------------------------------------------------------------------

    def show_disk_selection(self) -> str:
        if self._backend == "rich":
            return self._rich_disk_selection()
        return self._whiptail_disk_selection()

    def _rich_disk_selection(self) -> str:
        self._stop_progress()
        disks = _lsblk_disks()
        if not disks:
            raise TUIError("No suitable block devices found.")
        items = [
            (d["name"], f"{d['size']:>8}  {d['model'][:30]}") for d in disks
        ]
        return self._rich_select(
            "Disk Selection",
            "Select the target disk for installation.\n"
            "[bold red]WARNING: All data on the selected disk will be ERASED.[/]",
            items,
        )

    def _whiptail_disk_selection(self) -> str:
        disks = _lsblk_disks()
        if not disks:
            raise TUIError("No suitable block devices found.")
        items = [
            (d["name"], f"{d['size']:>8}  {d['model'][:30]}") for d in disks
        ]
        return self._select_from_list(
            "Disk Selection",
            "Select the target disk for installation.\n"
            "WARNING: All data on the selected disk will be ERASED.",
            items,
        )

    # ------------------------------------------------------------------
    # LUKS
    # ------------------------------------------------------------------

    def show_luks_prompt(self) -> bool:
        if self._backend == "rich":
            return self._rich_luks_prompt()
        return self._whiptail_luks_prompt()

    def _rich_luks_prompt(self) -> bool:
        assert self._console is not None
        self._stop_progress()
        self._console.print(
            Panel(
                Text.from_markup(
                    "Enable LUKS2 full-disk encryption?\n\n"
                    "You will be asked to set a passphrase.\n"
                    "Without encryption, data on the disk is accessible "
                    "to anyone with physical access."
                ),
                title="[bold]LUKS Encryption[/]",
                border_style="yellow",
            )
        )
        return Confirm.ask(
            "  Enable LUKS2 encryption?",
            default=False,
            console=self._console,
        )

    def _whiptail_luks_prompt(self) -> bool:
        rc, _ = _whiptail(
            *self._args(
                "--yesno",
                "Enable LUKS2 full-disk encryption?\n\n"
                "You will be asked to set a passphrase.\n"
                "Without encryption, data on the disk is accessible"
                " to anyone with physical access.",
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )
        return rc == 0

    # ------------------------------------------------------------------
    # TPM2 unlock
    # ------------------------------------------------------------------

    def show_tpm2_prompt(self) -> bool:
        """Ask whether to enable TPM2 auto-unlock for LUKS. Warns if no TPM2 detected."""
        import os
        tpm_available = os.path.exists("/sys/class/tpm/tpm0")
        warning = (
            ""
            if tpm_available
            else "\n\n[yellow]WARNING: No TPM2 device detected (/sys/class/tpm/tpm0 absent).\n"
            "You can still enable this — it will be configured but will fall\n"
            "back to passphrase if TPM2 is not present at boot.[/yellow]"
        )
        if self._backend == "rich":
            assert self._console is not None
            self._stop_progress()
            self._console.print(
                Panel(
                    Text.from_markup(
                        "Enable TPM2 auto-unlock for LUKS?\n\n"
                        "Binds the LUKS slot to TPM2 PCR 7+14 (Secure Boot state +\n"
                        "measured boot). The disk unlocks automatically at boot\n"
                        "without a passphrase — as long as the boot chain is unmodified.\n"
                        "Falls back to passphrase if measurements change."
                        + warning
                    ),
                    title="[bold]TPM2 Auto-Unlock[/]",
                    border_style="cyan",
                )
            )
            return Confirm.ask(
                "  Enable TPM2 auto-unlock?",
                default=False,
                console=self._console,
            )
        # whiptail fallback
        msg = (
            "Enable TPM2 auto-unlock for LUKS?\n\n"
            "Binds LUKS to TPM2 PCR 7+14 (Secure Boot + measured boot).\n"
            "Auto-unlocks at boot if the boot chain is unmodified."
        )
        if not tpm_available:
            msg += "\n\nWARNING: No TPM2 device detected. Will fall back to passphrase."
        rc, _ = _whiptail(
            *self._args("--yesno", msg, str(self._HEIGHT), str(self._WIDTH))
        )
        return rc == 0

    # ------------------------------------------------------------------
    # Passphrase
    # ------------------------------------------------------------------

    def show_passphrase_input(self) -> str:
        if self._backend == "rich":
            return self._rich_passphrase_input()
        return self._whiptail_passphrase_input()

    def _rich_passphrase_input(self) -> str:
        assert self._console is not None
        self._stop_progress()
        self._console.print(
            f"\n[bold blue]{self._title} - LUKS Passphrase[/]"
        )
        for attempt in range(3):
            passphrase = Prompt.ask(
                "  Enter LUKS encryption passphrase",
                password=True,
                console=self._console,
            )
            confirm = Prompt.ask(
                "  Confirm LUKS encryption passphrase",
                password=True,
                console=self._console,
            )
            if passphrase == confirm:
                if len(passphrase) < 4:
                    self._console.print(
                        "  [bold red]Passphrase must be at least 4 characters.[/]"
                    )
                    continue
                return passphrase
            self._console.print(
                f"  [bold red]Passphrases do not match. "
                f"Attempt {attempt + 1}/3.[/]"
            )
        raise TUIError("LUKS passphrase entry failed after 3 attempts.")

    def _whiptail_passphrase_input(self) -> str:
        for attempt in range(3):
            passphrase = self._password_box(
                "LUKS Passphrase", "Enter LUKS encryption passphrase:"
            )
            confirm = self._password_box(
                "LUKS Passphrase", "Confirm LUKS encryption passphrase:"
            )
            if passphrase == confirm:
                if len(passphrase) < 4:
                    self.show_error(
                        "Passphrase must be at least 4 characters.",
                        recoverable=True,
                    )
                    continue
                return passphrase
            self.show_error(
                f"Passphrases do not match. Attempt {attempt + 1}/3.",
                recoverable=True,
            )
        raise TUIError("LUKS passphrase entry failed after 3 attempts.")

    # ------------------------------------------------------------------
    # Partition preview
    # ------------------------------------------------------------------

    def show_partition_preview(self, disk: str, use_luks: bool) -> None:
        if self._backend == "rich":
            self._rich_partition_preview(disk, use_luks)
        else:
            self._whiptail_partition_preview(disk, use_luks)

    def _rich_partition_preview(self, disk: str, use_luks: bool) -> None:
        assert self._console is not None
        self._stop_progress()
        luks_tag = " (encrypted with LUKS2)" if use_luks else ""

        partitions = Table(
            title=f"Proposed layout for {disk}", show_lines=False
        )
        partitions.add_column("Partition", style="cyan")
        partitions.add_column("Size")
        partitions.add_column("Type")
        partitions.add_row("1", "512 MiB", "ESP (FAT32)")
        partitions.add_row("2", "remaining", f"Btrfs{luks_tag}")

        subvols = Table(title="Btrfs subvolumes", show_lines=False)
        subvols.add_column("Subvolume", style="cyan")
        subvols.add_column("Mount point")
        subvols.add_column("Note")
        subvols.add_row("@", "/", "read-only at boot")
        subvols.add_row("@var", "/var", "")
        subvols.add_row("@etc", "/etc", "")
        subvols.add_row("@home", "/home", "")
        subvols.add_row("@snapshots", "/.snapshots", "")
        subvols.add_row("[dim]Swap[/]", "[dim]zram[/]", "[dim]no swap partition[/]")

        self._console.print()
        self._console.print(partitions)
        self._console.print(subvols)
        self._countdown(10)

    def _whiptail_partition_preview(self, disk: str, use_luks: bool) -> None:
        luks_note = " (encrypted with LUKS2)" if use_luks else ""
        layout = (
            f"Proposed partition layout for {disk}:\n\n"
            f"  Partition 1:  512 MiB   ESP (FAT32)\n"
            f"  Partition 2:  remaining  Btrfs{luks_note}\n\n"
            f"Btrfs subvolumes:\n"
            f"  @            -> /           (read-only at boot)\n"
            f"  @var         -> /var\n"
            f"  @etc         -> /etc\n"
            f"  @home        -> /home\n"
            f"  @snapshots   -> /.snapshots\n\n"
            f"Swap: zram (no swap partition)"
        )
        _whiptail(
            *self._args(
                "--msgbox",
                layout,
                str(self._HEIGHT + 5),
                str(self._WIDTH),
            )
        )

    # ------------------------------------------------------------------
    # User creation
    # ------------------------------------------------------------------

    def show_user_creation(self) -> dict[str, str]:
        if self._backend == "rich":
            return self._rich_user_creation()
        return self._whiptail_user_creation()

    def _rich_user_creation(self) -> dict[str, str]:
        assert self._console is not None
        self._stop_progress()
        self._console.print(
            f"\n[bold blue]{self._title} - User Account[/]"
        )
        username = Prompt.ask(
            "  Enter username for the primary user",
            default="user",
            console=self._console,
        )
        for attempt in range(3):
            password = Prompt.ask(
                f"  Password for '{username}'",
                password=True,
                console=self._console,
            )
            confirm = Prompt.ask(
                "  Confirm password",
                password=True,
                console=self._console,
            )
            if password == confirm:
                if len(password) < 4:
                    self._console.print(
                        "  [bold red]Password must be at least 4 characters.[/]"
                    )
                    continue
                return {"username": username, "password_hash": _hash_password(password), "password": password}
            self._console.print(
                f"  [bold red]Passwords do not match. "
                f"Attempt {attempt + 1}/3.[/]"
            )
        raise TUIError("Password entry failed after 3 attempts.")

    def _whiptail_user_creation(self) -> dict[str, str]:
        username = self._input_box(
            "User Account",
            "Enter a username for the primary user account:",
            default="user",
        )
        for attempt in range(3):
            password = self._password_box(
                "User Account", f"Password for '{username}':"
            )
            confirm = self._password_box("User Account", "Confirm password:")
            if password == confirm:
                if len(password) < 4:
                    self.show_error(
                        "Password must be at least 4 characters.",
                        recoverable=True,
                    )
                    continue
                return {
                    "username": username,
                    "password_hash": _hash_password(password),
                    "password": password,
                }
            self.show_error(
                f"Passwords do not match. Attempt {attempt + 1}/3.",
                recoverable=True,
            )
        raise TUIError("Password entry failed after 3 attempts.")

    # ------------------------------------------------------------------
    # Secure Boot
    # ------------------------------------------------------------------

    def show_secure_boot_prompt(self) -> None:
        """Show Secure Boot setup instructions and wait for user acknowledgement."""
        if self._backend == "rich":
            self._rich_secure_boot_prompt()
        else:
            self._whiptail_secure_boot_prompt()

    def _rich_secure_boot_prompt(self) -> None:
        assert self._console is not None
        self._stop_progress()
        self._console.print(
            Panel(
                Text.from_markup(
                    "[bold yellow]Secure Boot requires your UEFI firmware to be in Setup Mode.[/]\n\n"
                    "Before the installer continues, please:\n\n"
                    "  1. [bold]Reboot[/] into your UEFI firmware settings\n"
                    "     (usually [bold]Del[/], [bold]F2[/], or [bold]F12[/] during POST)\n\n"
                    "  2. Navigate to [bold]Secure Boot[/] settings\n\n"
                    "  3. Select [bold]\"Clear Secure Boot Keys\"[/] or\n"
                    "     [bold]\"Delete All Secure Boot Variables\"[/]\n\n"
                    "  4. The firmware should now show [bold green]Setup Mode[/]\n\n"
                    "  5. Save and exit the firmware, then [bold]boot back into the installer[/]\n\n"
                    "[dim]sbctl will create and enroll your custom keys automatically.\n"
                    "Use[/] [bold]ouroboros-secureboot setup[/] [dim]after install to re-run if needed.[/]"
                ),
                title="[bold red]Secure Boot — Setup Mode Required[/]",
                border_style="red",
            )
        )
        Confirm.ask(
            "  I have put my firmware in Setup Mode and am ready to continue",
            default=True,
            console=self._console,
        )

    def _whiptail_secure_boot_prompt(self) -> None:
        msg = (
            "SECURE BOOT — Setup Mode Required\n\n"
            "Before continuing, put your UEFI firmware in Setup Mode:\n\n"
            "1. Reboot into UEFI firmware settings (Del/F2/F12 during POST)\n"
            "2. Navigate to Secure Boot settings\n"
            "3. Select 'Clear Secure Boot Keys' or 'Delete All Secure Boot Variables'\n"
            "4. Firmware should now show 'Setup Mode'\n"
            "5. Save and exit, then boot back into the installer\n\n"
            "sbctl will create and enroll your keys automatically."
        )
        _whiptail(
            *self._args(
                "--msgbox",
                msg,
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )

    # ------------------------------------------------------------------
    # WiFi connection
    # ------------------------------------------------------------------

    def show_wifi_connect(self) -> dict | None:
        """Show WiFi connection dialog.

        Returns ``{"ssid": ..., "passphrase": ...}`` on success, or ``None``.
        """
        if self._backend == "rich":
            return self._rich_wifi_connect()
        return self._whiptail_wifi_connect()

    def _find_wifi_interface(self) -> str | None:
        """Detect the first WiFi interface in managed (station) mode.

        Uses ``iw dev`` which reports ``type managed`` for client-mode
        interfaces (the nl80211 kernel constant is STATION but the
        display name is "managed").  We accept both strings for safety.

        A short retry loop (3 attempts × 2 s) covers the common case
        where the WiFi driver takes a moment to load after boot.
        """
        import time

        # Unblock WiFi if rfkill has it soft-blocked (common on laptops).
        rfkill = shutil.which("rfkill")
        if rfkill:
            subprocess.run(
                [rfkill, "unblock", "wifi"],
                capture_output=True, text=True, check=False,
            )

        for _attempt in range(3):
            result = subprocess.run(
                ["iw", "dev"], capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                time.sleep(2)
                continue
            iface: str | None = None
            is_managed = False
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("Interface "):
                    if is_managed and iface:
                        return iface
                    iface = stripped.split(maxsplit=1)[1]
                    is_managed = False
                elif stripped == "phy#":
                    if is_managed and iface:
                        return iface
                    iface = None
                    is_managed = False
                elif stripped in ("type managed", "type station"):
                    is_managed = True
            if is_managed and iface:
                return iface
            time.sleep(2)
        return None

    @staticmethod
    def _signal_to_bar(dbm: int) -> str:
        if dbm >= -50:
            return "▓▓▓▓▓▓"
        if dbm >= -60:
            return "▓▓▓▓▓░"
        if dbm >= -70:
            return "▓▓▓▓░░"
        if dbm >= -80:
            return "▓▓▓░░░"
        if dbm >= -85:
            return "▓▓░░░░"
        return "▓░░░░░"

    @staticmethod
    def _signal_quality(dbm: int) -> str:
        if dbm >= -50:
            return "Excellent"
        if dbm >= -60:
            return "Good"
        if dbm >= -70:
            return "Fair"
        if dbm >= -80:
            return "Weak"
        if dbm >= -85:
            return "Very Weak"
        return "Unusable"

    def _scan_wifi_networks(self, iface: str) -> list[tuple[str, str, int]]:
        """Scan WiFi networks via iwd + iw scan dump.

        Returns list of ``(ssid, security, signal_dbm)`` sorted by signal
        strength descending.  Security is ``"open"``, ``"WPA2"``, or
        ``"WPA3"``.
        """
        import time

        subprocess.run(
            ["iwctl", "station", iface, "scan"],
            capture_output=True, text=True, check=False,
        )
        time.sleep(5)

        result = subprocess.run(
            ["iw", "dev", iface, "scan", "dump"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return self._scan_wifi_fallback(iface)

        best: dict[str, tuple[str, int]] = {}
        current_ssid: str | None = None
        current_signal: int | None = None
        has_rsn = False
        has_wpa = False
        has_privacy = False

        for line in result.stdout.splitlines():
            s = line.strip()
            if s.startswith("BSS "):
                if current_ssid and current_signal is not None:
                    sec = self._classify_security(has_privacy, has_rsn, has_wpa)
                    prev = best.get(current_ssid)
                    if prev is None or current_signal > prev[1]:
                        best[current_ssid] = (sec, current_signal)
                current_ssid = None
                current_signal = None
                has_rsn = False
                has_wpa = False
                has_privacy = False
            elif s.startswith("SSID:"):
                current_ssid = s.split(":", 1)[1].strip()
                if not current_ssid or current_ssid.startswith("\\x00"):
                    current_ssid = None
            elif s.startswith("signal:"):
                try:
                    current_signal = int(float(s.split(":")[1].strip().split()[0]))
                except (ValueError, IndexError):
                    current_signal = None
            elif s.startswith("RSN:"):
                has_rsn = True
            elif s.startswith("WPA:"):
                has_wpa = True
            elif s.startswith("capability:") and "Privacy" in s:
                has_privacy = True

        if current_ssid and current_signal is not None:
            sec = self._classify_security(has_privacy, has_rsn, has_wpa)
            prev = best.get(current_ssid)
            if prev is None or current_signal > prev[1]:
                best[current_ssid] = (sec, current_signal)

        networks = [(ssid, sec, dbm) for ssid, (sec, dbm) in best.items()]
        networks.sort(key=lambda n: n[2], reverse=True)
        return networks

    @staticmethod
    def _classify_security(has_privacy: bool, has_rsn: bool, has_wpa: bool) -> str:
        if has_rsn:
            return "WPA2"
        if has_wpa:
            return "WPA1"
        if has_privacy:
            return "WPA"
        return "open"

    def _scan_wifi_fallback(self, iface: str) -> list[tuple[str, str, int]]:
        """Fallback: parse ``iwctl get-networks`` when ``iw scan dump`` fails."""
        result = subprocess.run(
            ["iwctl", "station", iface, "get-networks"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return []
        networks: list[tuple[str, str, int]] = []
        in_table = False
        for line in result.stdout.splitlines():
            s = line.strip()
            if s.startswith("----"):
                in_table = True
                continue
            if not in_table or not s:
                continue
            parts = s.split()
            if len(parts) < 3:
                continue
            ssid = parts[0]
            security = parts[1]
            asterisks = parts[-1].count("*")
            dbm = -40 - (6 - asterisks) * 10 if asterisks else -90
            networks.append((ssid, security, dbm))
        networks.sort(key=lambda n: n[2], reverse=True)
        return networks

    def _rich_wifi_connect(self) -> bool:
        assert self._console is not None
        self._stop_progress()
        PAGE_SIZE = 10

        self._console.print(Panel(
            Text.from_markup(
                "No internet connectivity detected.\n\n"
                "Select a WiFi network to connect to."
            ),
            title="[bold]Network Configuration[/]",
            border_style="yellow",
        ))

        iface = self._find_wifi_interface()
        if iface is None:
            self._console.print("  [bold red]No WiFi interface found.[/]")
            return None

        networks: list[tuple[str, str, int]] = []
        page = 0

        while True:
            if not networks:
                self._console.print("  [dim]Scanning for networks...[/]")
                networks = self._scan_wifi_networks(iface)
                if not networks:
                    self._console.print("  [bold red]No WiFi networks found.[/]")
                    action = Prompt.ask(
                        "  [R] Re-scan  [M] Manual SSID  [0] Skip",
                        default="0", console=self._console,
                    ).strip().lower()
                    if action == "r":
                        continue
                    if action == "m":
                        return self._manual_wifi_connect(iface)
                    return None
                page = 0

            total_pages = max(1, -(-len(networks) // PAGE_SIZE))
            start = page * PAGE_SIZE
            end = min(start + PAGE_SIZE, len(networks))
            page_networks = networks[start:end]

            table = Table(
                title=f"Available Networks (page {page + 1}/{total_pages})",
                show_lines=False,
            )
            table.add_column("#", style="cyan bold", width=4)
            table.add_column("SSID", style="bold", min_width=22)
            table.add_column("Security", width=10)
            table.add_column("Signal", min_width=20)
            for i, (ssid, security, dbm) in enumerate(page_networks, start=start + 1):
                bar = self._signal_to_bar(dbm)
                quality = self._signal_quality(dbm)
                table.add_row(
                    str(i), ssid, security,
                    f"{bar}  {dbm} dBm  {quality}",
                )
            self._console.print(table)

            nav = []
            if page > 0:
                nav.append("[P] Prev page")
            if page < total_pages - 1:
                nav.append("[N] Next page")
            nav_parts = "  ".join(nav)
            prompt_text = (
                f"  [{start}-{end}] Select  [R] Re-scan  [M] Manual  {nav_parts}  [0] Skip"
            ).strip()

            choice = Prompt.ask(
                prompt_text, default="0", console=self._console,
            ).strip().lower()

            if choice == "0":
                return None
            if choice == "r":
                networks = []
                continue
            if choice == "m":
                return self._manual_wifi_connect(iface)
            if choice == "n" and page < total_pages - 1:
                page += 1
                continue
            if choice == "p" and page > 0:
                page -= 1
                continue

            try:
                idx = int(choice) - 1
            except ValueError:
                continue
            if idx < 0 or idx >= len(networks):
                continue

            ssid, security, _dbm = networks[idx]
            creds = self._attempt_wifi_connection(iface, ssid, security)
            if creds is not None:
                return creds
            self._console.print(
                "  [bold yellow]Press Enter to return to network list...[/]"
            )
            Prompt.ask("", console=self._console)
            networks = []

    def _manual_wifi_connect(self, iface: str) -> bool:
        assert self._console is not None
        self._console.print(Panel(
            Text.from_markup(
                "Enter the network name manually.\n"
                "Use this for hidden / non-broadcasting SSIDs."
            ),
            title="[bold]Manual Connection[/]",
            border_style="yellow",
        ))
        ssid = Prompt.ask("  SSID", console=self._console).strip()
        if not ssid:
            return None
        password = Prompt.ask(
            f"  Password for '{ssid}' (leave empty for open network)",
            password=True, console=self._console,
        )
        security = "open" if not password else "WPA2"
        return self._attempt_wifi_connection(iface, ssid, security, password or None)

    def _attempt_wifi_connection(
        self, iface: str, ssid: str, security: str, password: str | None = None,
    ) -> dict | None:
        assert self._console is not None
        import time

        self._console.print(f"  Connecting to [bold]{ssid}[/]...")
        if security == "open":
            cmd = ["iwctl", "station", iface, "connect", ssid]
        elif password:
            cmd = [
                "iwctl", "--passphrase", password,
                "station", iface, "connect", ssid,
            ]
        else:
            password = Prompt.ask(
                f"  Password for '{ssid}'", password=True, console=self._console,
            )
            cmd = [
                "iwctl", "--passphrase", password,
                "station", iface, "connect", ssid,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            self._console.print(
                f"  [bold red]Connection failed: {result.stderr.strip()}[/]"
            )
            return None

        time.sleep(5)
        ping = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, check=False,
        )
        if ping.returncode == 0:
            self._console.print("  [bold green]✅ Connected! Internet OK[/]")
            return {"ssid": ssid, "passphrase": password or ""}
        self._console.print("  [bold red]Connected but no internet.[/]")
        return None

    def _whiptail_wifi_connect(self) -> dict | None:
        iface = self._find_wifi_interface()
        if iface is None:
            self.show_error("No WiFi interface found.", recoverable=False)
            return None

        networks = self._scan_wifi_networks(iface)
        if not networks:
            self.show_error("No WiFi networks found.", recoverable=False)
            return None

        items = [
            (ssid, f"{security}  {self._signal_to_bar(dbm)}  {dbm}dBm")
            for ssid, security, dbm in networks
        ]
        items.append(("skip", "Skip / Retry later"))
        ssid = self._select_from_list(
            "WiFi Networks", "Select a network:", items,
        )
        if ssid == "skip":
            return None

        selected = [(s, sec, dbm) for s, sec, dbm in networks if s == ssid]
        if not selected:
            return None
        _ssid, security, _dbm = selected[0]

        password = None
        if security != "open":
            password = self._password_box("WiFi", f"Password for '{_ssid}':")

        if security == "open":
            cmd = ["iwctl", "station", iface, "connect", _ssid]
        else:
            cmd = [
                "iwctl", "--passphrase", password or "",
                "station", iface, "connect", _ssid,
            ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            self.show_error(f"Connection failed: {result.stderr.strip()}", recoverable=False)
            return None

        import time
        time.sleep(5)
        ping = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, check=False,
        )
        if ping.returncode == 0:
            return {"ssid": _ssid, "passphrase": password or ""}
        return None

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def show_summary(self, config: Any) -> None:
        if self._backend == "rich":
            self._rich_summary(config)
        else:
            self._whiptail_summary(config)

    def _rich_summary(self, config: Any) -> None:
        assert self._console is not None
        self._stop_progress()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim bold")
        table.add_column(style="bold green")
        table.add_row("Disk", config.disk.device)
        table.add_row("LUKS", "Yes" if config.disk.use_luks else "No")
        table.add_row("Hostname", config.network.hostname)
        table.add_row("User", config.user.username)
        table.add_row("Locale", config.locale.locale)
        table.add_row("Timezone", config.locale.timezone)
        self._console.print()
        self._console.print(
            Panel(
                table,
                title="[bold green]Installation Complete[/]",
                border_style="green",
                padding=(1, 2),
            )
        )
        self._console.print("\n  Remove the installation media.\n")

    def _whiptail_summary(self, config: Any) -> None:
        text = (
            "Installation Complete!\n\n"
            f"  Disk:      {config.disk.device}\n"
            f"  LUKS:      {'Yes' if config.disk.use_luks else 'No'}\n"
            f"  Hostname:  {config.network.hostname}\n"
            f"  User:      {config.user.username}\n"
            f"  Locale:    {config.locale.locale}\n"
            f"  Timezone:  {config.locale.timezone}\n\n"
            "Remove the installation media."
        )
        _whiptail(
            *self._args(
                "--msgbox",
                text,
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )

    # ------------------------------------------------------------------
    # Post-install action
    # ------------------------------------------------------------------

    def show_post_install_action(self) -> str:
        """Ask the user whether to reboot or shutdown after installation.

        Returns ``"reboot"`` or ``"shutdown"``.
        """
        if self._backend == "rich":
            return self._rich_post_install_action()
        return self._whiptail_post_install_action()

    def _rich_post_install_action(self) -> str:
        return self._rich_select(
            title="What next?",
            prompt="Choose what to do after installation:",
            items=[
                ("reboot", "Restart the system now"),
                ("shutdown", "Shut the system down"),
            ],
            default="reboot",
        )

    def _whiptail_post_install_action(self) -> str:
        rc, _ = _whiptail(
            *self._args(
                "--yesno",
                "Restart the system now?\n\nYes = Reboot   No = Shutdown",
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )
        return "reboot" if rc == 0 else "shutdown"

    # ------------------------------------------------------------------
    # Error
    # ------------------------------------------------------------------

    def show_error(self, message: str, recoverable: bool = True) -> bool:
        if self._backend == "rich":
            return self._rich_error(message, recoverable)
        return self._whiptail_error(message, recoverable)

    def _rich_error(self, message: str, recoverable: bool) -> bool:
        assert self._console is not None
        self._stop_progress()
        self._console.print()
        self._console.print(
            Panel(
                Text.from_markup(f"[bold red]Error:[/]\n\n{message}"),
                border_style="red",
                padding=(1, 2),
            )
        )
        if recoverable:
            return Confirm.ask(
                "  Retry?", default=True, console=self._console
            )
        return False

    def _whiptail_error(self, message: str, recoverable: bool) -> bool:
        if recoverable:
            rc, _ = _whiptail(
                *self._args(
                    "--yesno",
                    f"Error:\n\n{message}\n\nRetry?",
                    str(self._HEIGHT),
                    str(self._WIDTH),
                    "--yes-button",
                    "Retry",
                    "--no-button",
                    "Abort",
                )
            )
            return rc == 0
        _whiptail(
            *self._args(
                "--msgbox",
                f"Fatal Error:\n\n{message}\n\nThe installer will exit.",
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )
        return False

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def show_confirmation(self, message: str) -> bool:
        if self._backend == "rich":
            return self._rich_confirmation(message)
        return self._whiptail_confirmation(message)

    def _rich_confirmation(self, message: str) -> bool:
        assert self._console is not None
        self._stop_progress()
        self._console.print()
        return Confirm.ask(
            f"  {message}", default=False, console=self._console
        )

    def _whiptail_confirmation(self, message: str) -> bool:
        rc, _ = _whiptail(
            *self._args(
                "--yesno",
                message,
                str(self._HEIGHT),
                str(self._WIDTH),
            )
        )
        return rc == 0

    # ------------------------------------------------------------------
    # Rich private helpers
    # ------------------------------------------------------------------

    def _rich_select(
        self,
        title: str,
        prompt: str,
        items: list[tuple[str, str]],
        default: str = "",
    ) -> str:
        assert self._console is not None
        self._stop_progress()
        self._console.print()
        self._console.print(
            Panel(
                Text.from_markup(prompt),
                title=f"[bold]{title}[/]",
                border_style="blue",
            )
        )
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Num", style="cyan bold", width=4)
        table.add_column("Value", style="bold")
        table.add_column("Description")
        default_idx = 1
        for i, (value, desc) in enumerate(items):
            row_desc = Text(desc)
            if value == default:
                row_desc.append("  <- default", style="dim")
                default_idx = i + 1
            table.add_row(str(i + 1), value, row_desc)
        self._console.print(table)

        while True:
            choice = IntPrompt.ask(
                f"  Select [1-{len(items)}]",
                default=default_idx,
                console=self._console,
            )
            if 1 <= choice <= len(items):
                return items[choice - 1][0]
            self._console.print(
                f"  [red]Please enter a number between 1 and {len(items)}[/]"
            )

    def _rich_input(
        self, title: str, prompt: str, default: str = ""
    ) -> str:
        assert self._console is not None
        self._stop_progress()
        self._console.print(
            f"\n[bold blue]{self._title} - {title}[/]"
        )
        return Prompt.ask(
            f"  {prompt}", default=default, console=self._console
        )

    # ------------------------------------------------------------------
    # Whiptail private helpers
    # ------------------------------------------------------------------

    def _select_from_list(
        self,
        title: str,
        prompt: str,
        items: list[tuple[str, str]],
        default: str = "",
    ) -> str:
        flat: list[str] = []
        for value, desc in items:
            tag = "ON" if value == default else "OFF"
            flat += [value, desc, tag]

        rc, selection = _whiptail(
            "--title",
            f"{self._title} - {title}",
            "--radiolist",
            prompt,
            str(self._HEIGHT),
            str(self._WIDTH),
            str(len(items)),
            *flat,
        )
        if rc != 0:
            raise TUIError(f"User cancelled selection: {title}")
        return selection

    def _input_box(self, title: str, prompt: str, default: str = "") -> str:
        rc, value = _whiptail(
            "--title",
            f"{self._title} - {title}",
            "--inputbox",
            prompt,
            str(self._HEIGHT),
            str(self._WIDTH),
            default,
        )
        if rc != 0:
            raise TUIError(f"User cancelled input: {title}")
        return value

    def _password_box(self, title: str, prompt: str) -> str:
        rc, value = _whiptail(
            "--title",
            f"{self._title} - {title}",
            "--passwordbox",
            prompt,
            str(self._HEIGHT),
            str(self._WIDTH),
        )
        if rc != 0:
            raise TUIError(f"User cancelled password entry: {title}")
        return value

    # ------------------------------------------------------------------
    # Remote config prompt
    # ------------------------------------------------------------------

    def show_remote_config_prompt(self) -> str | None:
        """Ask user if they want to use a remote configuration file.

        Returns:
            URL string if user provides one, None if declined.
        """
        if self._backend == "rich":
            return self._rich_remote_config_prompt()
        return self._whiptail_remote_config_prompt()

    def _rich_remote_config_prompt(self) -> str | None:
        assert self._console is not None
        self._stop_progress()

        self._console.print(
            Panel(
                "\nNo local configuration file found.\n\n"
                "You can provide a URL to a YAML configuration file\n"
                "(e.g. a GitHub raw URL) for unattended installation.\n",
                title="[bold cyan]Remote Configuration[/]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

        choice = Confirm.ask(
            "  Use a remote configuration file?",
            default=False,
            console=self._console,
        )
        if not choice:
            return None

        url = Prompt.ask(
            "  Enter config URL",
            console=self._console,
        )
        return url.strip() or None

    def _whiptail_remote_config_prompt(self) -> str | None:
        # Yes/No dialog first
        rc, _ = _whiptail(
            "--title", f"{self._title} - Remote Configuration",
            "--yesno",
            "No local configuration file found.\n\n"
            "Do you want to use a remote configuration file\n"
            "for unattended installation?",
            str(self._HEIGHT), str(self._WIDTH),
        )
        if rc != 0:
            return None

        # URL input
        rc, url = _whiptail(
            "--title", f"{self._title} - Remote Configuration",
            "--inputbox",
            "Enter the URL to the YAML configuration file\n"
            "(e.g. https://raw.githubusercontent.com/.../config.yaml):",
            str(self._HEIGHT), str(self._WIDTH),
            "",
        )
        if rc != 0:
            return None
        return url.strip() or None
