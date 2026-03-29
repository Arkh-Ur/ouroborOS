"""tui.py — ouroborOS installer TUI layer.

Wraps whiptail to provide all user-interaction screens.
All TUI functions return structured data; they never modify global state.

Requirements:
    - whiptail must be installed on the system (from newt package)
    - Terminal must be at least 80x24
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


class TUIError(Exception):
    """Raised when a TUI operation fails (e.g. whiptail not available)."""


def _get_whiptail_path() -> str:
    """Resolve whiptail binary path, Returns the fixed path or raises TUIError."""
    path = shutil.which("whiptail")
    if path is None:
        raise TUIError("whiptail is not installed. Install 'libnewt' or 'newt' package.")
    return path


def _whiptail(*args: str, input_text: str | None = None) -> tuple[int, str]:
    """Run a whiptail command and return (returncode, stdout).

    Args:
        *args:      whiptail arguments.
        input_text: Optional text to pass to stdin.

    Returns:
        Tuple of (returncode, stdout_text). whiptail writes the selection
        to stderr, so we redirect stderr→stdout capture.
    """
    cmd = [_get_whiptail_path()] + list(args)
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    # whiptail writes user selection to stderr
    return result.returncode, result.stderr.strip()


def _lsblk_disks() -> list[dict[str, str]]:
    """Return a list of block devices suitable for installation.

    Returns:
        List of dicts with 'name', 'size', 'model' keys.
        Only whole disks (not partitions) are returned.
    """
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
    """Return a SHA-512 crypt hash of the given password.

    Uses the same format as /etc/shadow: $6$<salt>$<hash>.
    The Python crypt module was removed in Python 3.13; uses openssl instead.
    """
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

    All show_* methods interact with the user and return structured data.
    They raise TUIError if whiptail is unavailable or the user cancels.
    """

    # Default dialog dimensions
    _HEIGHT = 20
    _WIDTH = 72

    def __init__(self, title: str = "ouroborOS Installer") -> None:
        self._title = title
        self._check_whiptail()

    def _check_whiptail(self) -> None:
        if shutil.which("whiptail") is None:
            raise TUIError(
                "whiptail is not installed. Install 'libnewt' or 'newt' package."
            )

    def _args(self, *extra: str) -> list[str]:
        """Prepend standard title args."""
        return ["--title", self._title] + list(extra)

    # --- Welcome screen -----------------------------------------------------

    def show_welcome(self) -> None:
        """Display the welcome/intro screen."""
        text = (
            "Welcome to the ouroborOS installer.\n\n"
            "ouroborOS is an ArchLinux-based distribution with an immutable\n"
            "Btrfs root filesystem and a fully systemd-native stack.\n\n"
            "This installer will guide you through the installation process.\n\n"
            "WARNING: This will ERASE the target disk completely."
        )
        _whiptail(
            *self._args(
                "--msgbox", text,
                str(self._HEIGHT), str(self._WIDTH),
            )
        )

    # --- Locale menu --------------------------------------------------------

    def show_locale_menu(self) -> dict[str, str]:
        """Show locale/timezone/keymap selection.

        Returns:
            Dict with keys: 'locale', 'keymap', 'timezone'.
        """
        locale = self._select_from_list(
            "Locale",
            "Select system locale:",
            [
                ("en_US.UTF-8", "English (US) — UTF-8"),
                ("en_GB.UTF-8", "English (UK) — UTF-8"),
                ("es_ES.UTF-8", "Spanish (Spain) — UTF-8"),
                ("es_MX.UTF-8", "Spanish (Mexico) — UTF-8"),
                ("fr_FR.UTF-8", "French (France) — UTF-8"),
                ("de_DE.UTF-8", "German (Germany) — UTF-8"),
                ("pt_BR.UTF-8", "Portuguese (Brazil) — UTF-8"),
                ("ja_JP.UTF-8", "Japanese — UTF-8"),
                ("zh_CN.UTF-8", "Chinese Simplified — UTF-8"),
            ],
            default="en_US.UTF-8",
        )

        keymap = self._select_from_list(
            "Keyboard Layout",
            "Select keyboard layout:",
            [
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
            ],
            default="us",
        )

        timezone = self._input_box(
            "Timezone",
            "Enter timezone (e.g. America/New_York, Europe/Madrid, UTC):",
            default="UTC",
        )

        return {"locale": locale, "keymap": keymap, "timezone": timezone}

    def show_hostname_input(self) -> str:
        """Prompt for system hostname.

        Returns:
            Hostname string (validated by caller).
        """
        return self._input_box(
            "Hostname",
            "Enter a hostname for the installed system:",
            default="ouroboros",
        )

    # --- Disk selection -----------------------------------------------------

    def show_disk_selection(self) -> str:
        """Show available disks and let the user pick one.

        Returns:
            Selected disk device path (e.g. /dev/sda).

        Raises:
            TUIError: If no disks are available or user cancels.
        """
        disks = _lsblk_disks()
        if not disks:
            raise TUIError("No suitable block devices found.")

        items: list[tuple[str, str]] = [
            (d["name"], f"{d['size']:>8}  {d['model'][:30]}")
            for d in disks
        ]

        return self._select_from_list(
            "Disk Selection",
            "Select the target disk for installation.\n"
            "WARNING: All data on the selected disk will be ERASED.",
            items,
        )

    def show_luks_prompt(self) -> bool:
        """Ask whether to enable LUKS encryption.

        Returns:
            True if the user wants LUKS encryption.
        """
        rc, _ = _whiptail(
            *self._args(
                "--yesno",
                "Enable LUKS2 full-disk encryption?\n\n"
                "You will be asked to set a passphrase.\n"
                "Without encryption, data on the disk is accessible"
                " to anyone with physical access.",
                str(self._HEIGHT), str(self._WIDTH),
            )
        )
        return rc == 0

    def show_passphrase_input(self) -> str:
        """Prompt for LUKS passphrase with confirmation.

        Returns:
            The passphrase string.

        Raises:
            TUIError: If the passphrases don't match after 3 attempts.
        """
        for attempt in range(3):
            passphrase = self._password_box(
                "LUKS Passphrase",
                "Enter LUKS encryption passphrase:",
            )
            confirm = self._password_box(
                "LUKS Passphrase",
                "Confirm LUKS encryption passphrase:",
            )
            if passphrase == confirm:
                if len(passphrase) < 8:
                    self.show_error(
                        "Passphrase must be at least 8 characters.", recoverable=True
                    )
                    continue
                return passphrase
            self.show_error(
                f"Passphrases do not match. Attempt {attempt + 1}/3.", recoverable=True
            )
        raise TUIError("LUKS passphrase entry failed after 3 attempts.")

    # --- Partition preview --------------------------------------------------

    def show_partition_preview(self, disk: str, use_luks: bool) -> None:
        """Show the proposed partition layout before applying.

        Args:
            disk:     Target disk device.
            use_luks: Whether LUKS is enabled.
        """
        luks_note = " (encrypted with LUKS2)" if use_luks else ""
        layout = (
            f"Proposed partition layout for {disk}:\n\n"
            f"  Partition 1:  512 MiB   ESP (FAT32)\n"
            f"  Partition 2:  remaining  Btrfs{luks_note}\n\n"
            f"Btrfs subvolumes:\n"
            f"  @            → /           (read-only at boot)\n"
            f"  @var         → /var\n"
            f"  @etc         → /etc\n"
            f"  @home        → /home\n"
            f"  @snapshots   → /.snapshots\n\n"
            f"Swap: zram (no swap partition)"
        )
        _whiptail(
            *self._args(
                "--msgbox", layout,
                str(self._HEIGHT + 5), str(self._WIDTH),
            )
        )

    # --- User creation ------------------------------------------------------

    def show_user_creation(self) -> dict[str, str]:
        """Prompt for username and password.

        Returns:
            Dict with 'username' and 'password_hash'.

        Raises:
            TUIError: If passwords don't match after 3 attempts.
        """
        username = self._input_box(
            "User Account",
            "Enter a username for the primary user account:",
            default="user",
        )

        for attempt in range(3):
            password = self._password_box("User Account", f"Password for '{username}':")
            confirm = self._password_box("User Account", "Confirm password:")
            if password == confirm:
                if len(password) < 6:
                    self.show_error(
                        "Password must be at least 6 characters.", recoverable=True
                    )
                    continue
                return {"username": username, "password_hash": _hash_password(password)}
            self.show_error(
                f"Passwords do not match. Attempt {attempt + 1}/3.", recoverable=True
            )

        raise TUIError("Password entry failed after 3 attempts.")

    # --- Progress gauge -----------------------------------------------------

    def show_progress(self, title: str, text: str, percent: int) -> None:
        """Display a progress gauge (non-blocking informational update)."""
        whiptail = _get_whiptail_path()
        if whiptail is None:
            return
        subprocess.run(
                [
                    _get_whiptail_path(),
                    "--title", title,
                    "--gauge", text,
                    str(self._HEIGHT), str(self._WIDTH),
                    str(max(0, min(100, percent))),
                ],
                input="",
                capture_output=True,
                text=True,
                check=False,
            )

    # --- Summary screen -----------------------------------------------------

    def show_summary(self, config: Any) -> None:
        """Show installation complete summary.

        Args:
            config: The InstallerConfig used for installation.
        """
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
                "--msgbox", text,
                str(self._HEIGHT), str(self._WIDTH),
            )
        )

    # --- Error screen -------------------------------------------------------

    def show_error(self, message: str, recoverable: bool = True) -> bool:
        """Display an error message.

        Args:
            message:     Error description.
            recoverable: If True, offer Retry/Abort options.
                         If False, show OK only (fatal).

        Returns:
            True if user chose to retry, False to abort.
        """
        if recoverable:
            rc, _ = _whiptail(
                *self._args(
                    "--yesno",
                    f"Error:\n\n{message}\n\nRetry?",
                    str(self._HEIGHT), str(self._WIDTH),
                    "--yes-button", "Retry",
                    "--no-button", "Abort",
                )
            )
            return rc == 0
        else:
            _whiptail(
                *self._args(
                    "--msgbox",
                    f"Fatal Error:\n\n{message}\n\nThe installer will exit.",
                    str(self._HEIGHT), str(self._WIDTH),
                )
            )
            return False

    # --- Confirmation dialog -------------------------------------------------

    def show_confirmation(self, message: str) -> bool:
        """Show a yes/no confirmation dialog.

        Returns:
            True if user confirmed (Yes), False otherwise.
        """
        rc, _ = _whiptail(
            *self._args(
                "--yesno", message,
                str(self._HEIGHT), str(self._WIDTH),
            )
        )
        return rc == 0

    # --- Private helpers ----------------------------------------------------

    def _select_from_list(
        self,
        title: str,
        prompt: str,
        items: list[tuple[str, str]],
        default: str = "",
    ) -> str:
        """Show a whiptail menu and return the selected item value.

        Args:
            title:   Section title appended to the window title.
            prompt:  Prompt text above the list.
            items:   List of (value, description) tuples.
            default: Pre-selected value (if present).

        Returns:
            The selected value string.

        Raises:
            TUIError: If user cancels (ESC or Cancel).
        """
        flat: list[str] = []
        for value, desc in items:
            tag = "ON" if value == default else "OFF"
            flat += [value, desc, tag]

        rc, selection = _whiptail(
            "--title", f"{self._title} — {title}",
            "--radiolist", prompt,
            str(self._HEIGHT), str(self._WIDTH),
            str(len(items)),
            *flat,
        )
        if rc != 0:
            raise TUIError(f"User cancelled selection: {title}")
        return selection

    def _input_box(self, title: str, prompt: str, default: str = "") -> str:
        """Show a whiptail input box.

        Returns:
            The entered string.

        Raises:
            TUIError: If user cancels.
        """
        rc, value = _whiptail(
            "--title", f"{self._title} — {title}",
            "--inputbox", prompt,
            str(self._HEIGHT), str(self._WIDTH),
            default,
        )
        if rc != 0:
            raise TUIError(f"User cancelled input: {title}")
        return value

    def _password_box(self, title: str, prompt: str) -> str:
        """Show a whiptail password box (input masked).

        Returns:
            The entered password string.

        Raises:
            TUIError: If user cancels.
        """
        rc, value = _whiptail(
            "--title", f"{self._title} — {title}",
            "--passwordbox", prompt,
            str(self._HEIGHT), str(self._WIDTH),
        )
        if rc != 0:
            raise TUIError(f"User cancelled password entry: {title}")
        return value
