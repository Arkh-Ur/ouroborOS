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
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
    from rich.text import Text

    HAS_RICH = True
except ImportError:
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
        self._progress: Progress | None = None
        self._progress_task_id: int | None = None
        self._progress_title: str = ""

        if HAS_RICH:
            self._backend = "rich"
            self._console: Console | None = Console()
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
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._progress_task_id = None
            self._progress_title = ""

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
        Prompt.ask(
            "\n  [dim]Press Enter to continue[/]",
            default="",
            console=self._console,
        )

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

        if self._progress is not None and self._progress_title != title:
            self._stop_progress()

        if self._progress is None:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn(f"[bold blue]{title}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("{task.description}"),
                console=self._console,
                transient=False,
            )
            self._progress.start()
            self._progress_task_id = self._progress.add_task(
                text, total=100, completed=pct
            )
            self._progress_title = title
        else:
            assert self._progress_task_id is not None
            self._progress.update(
                self._progress_task_id,
                description=text,
                completed=pct,
            )

        self._progress.refresh()

        if pct >= 100:
            self._stop_progress()

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
                if len(passphrase) < 8:
                    self._console.print(
                        "  [bold red]Passphrase must be at least 8 characters.[/]"
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
                if len(passphrase) < 8:
                    self.show_error(
                        "Passphrase must be at least 8 characters.",
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
        Prompt.ask(
            "\n  [dim]Press Enter to continue[/]",
            default="",
            console=self._console,
        )

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
                if len(password) < 6:
                    self._console.print(
                        "  [bold red]Password must be at least 6 characters.[/]"
                    )
                    continue
                return {"username": username, "password_hash": _hash_password(password)}
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
                if len(password) < 6:
                    self.show_error(
                        "Password must be at least 6 characters.",
                        recoverable=True,
                    )
                    continue
                return {
                    "username": username,
                    "password_hash": _hash_password(password),
                }
            self.show_error(
                f"Passwords do not match. Attempt {attempt + 1}/3.",
                recoverable=True,
            )
        raise TUIError("Password entry failed after 3 attempts.")

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
        self._console.print(
            "\n  Remove the installation media and press Enter to reboot."
        )
        Prompt.ask(
            "  [dim]Press Enter to continue[/]",
            default="",
            console=self._console,
        )

    def _whiptail_summary(self, config: Any) -> None:
        text = (
            "Installation Complete!\n\n"
            f"  Disk:      {config.disk.device}\n"
            f"  LUKS:      {'Yes' if config.disk.use_luks else 'No'}\n"
            f"  Hostname:  {config.network.hostname}\n"
            f"  User:      {config.user.username}\n"
            f"  Locale:    {config.locale.locale}\n"
            f"  Timezone:  {config.locale.timezone}\n\n"
            "Remove the installation media and press Enter to reboot."
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
