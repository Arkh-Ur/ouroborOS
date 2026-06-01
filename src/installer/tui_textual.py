"""tui_textual.py — Textual-based two-panel TUI for the ouroborOS installer.

This module provides the v0.6.0 Textual UI. It implements the same 25 show_*
interface methods expected by the ouroborOS installer state machine, backed by
a full-screen two-panel Textual application.

Architecture:
- The Textual app (InstallerApp) runs on the main thread.
- The FSM runs in a background worker thread.
- Communication is via threading.Queue (response_queue): FSM blocks on .get(),
  TUI puts values in via call_from_thread.
- TUIBuffer holds pre-filled values from the two-panel menu. If a value is
  already in the buffer, show_* returns it immediately (non-blocking).
"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any

from installer.i18n import init_i18n

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGO = (
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⠀⠀⠀\n"
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣿⣿⡿⠿⠿⣿⣿⣶⣄⠀⠀⠀⠀⢀⣾⣿⡿⠿⢿⣿⣷⠀\n"
    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⣿⠋⠀⠀⠀⠀⠀⠀⠻⣿⣧⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠉⠀\n"
    "⠀⠀⣤⣶⣿⣿⣷⣤⠀⠀⠀⠀⣿⡇⠀⠀⠀⠀⢸⣿⠀⠀⠀⣿⡇⢀⣶⣿⣿⠀⠀⠀⣤⣶⣿⣿⣷⣤⠀⠀⠀⠀⣿⣿⢀⣶⣿⣿⣶⣄⠀⠀⠀⠀⣠⣶⣿⣿⣿⣦⡀⠀⠀⠀⣿⣿⠀⣴⣿⣿⠆⠀⣿⣿⠁⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⡆⠀⠀⣿⣿⡀⠀⠀⠀⠀⠀⠀\n"
    "⢀⣿⡿⠁⠀⠀⠀⢻⣿⡀⠀⠀⣿⡇⠀⠀⠀⠀⢸⣿⠀⠀⠀⣿⣷⠟⠁⠀⠀⠀⢀⣿⡿⠁⠀⠀⠀⢻⣿⡀⠀⠀⣿⣿⠋⠀⠀⠀⠹⣿⡆⠀⠀⣾⣿⠋⠀⠀⠀⠙⣿⣆⠀⠀⣿⣿⡿⠉⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠈⠿⣿⣿⣶⣤⡀⠀⠀\n"
    "⣼⣿⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⣿⡇⠀⠀⠀⠀⢸⣿⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⣼⣿⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⣿⣿⠀⠀⠀⠀⠀⣿⣿⠀⢠⣿⡇⠀⠀⠀⠀⠀⢿⣿⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠉⠙⠿⣿⣷⡀\n"
    "⣿⣿⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⣿⡇⠀⠀⠀⠀⢸⣿⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⣿⣿⠀⠀⠀⠀⠀⣿⣿⠀⢸⣿⡇⠀⠀⠀⠀⠀⣸⣿⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⣸⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣧\n"
    "⠸⣿⣆⠀⠀⠀⠀⢠⣿⠏⠀⠀⣿⣇⠀⠀⠀⠀⣸⣿⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠸⣿⣆⠀⠀⠀⠀⢠⣿⠏⠀⠀⣿⣿⠀⠀⠀⠀⢠⣿⡏⠀⠀⣿⣷⠀⠀⠀⠀⠀⣿⡿⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠈⣿⣿⣄⠀⠀⠀⠀⠀⠀⣴⣿⡟⠀⠀⠀⣤⡀⠀⠀⠀⠀⣠⣿⠇\n"
    "⠀⠙⣿⣷⣤⣤⣶⣿⠋⠀⠀⠀⠻⣿⣶⣤⣴⡿⢻⣿⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠙⣿⣷⣤⣤⣶⣿⠋⠀⠀⠀⣿⡿⣷⣦⣤⣶⣿⠟⠀⠀⠀⠈⢿⣿⣦⣤⣶⣿⠟⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠛⣿⣿⣷⣶⣶⣿⣿⡿⠋⠀⠀⠀⠈⠿⣿⣿⣶⣶⣿⣿⠋⠀\n"
    "⠀⠀⠀⠀⠉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠉⠀⠀⠀⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠁⠀⠀⠀⠀⠀⠉⠁⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠉⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠁⠀⠀⠀"
)

LOCALE_CATALOG: list[tuple[str, str, str]] = [
    ("English (US)", "en_US", "en_US"),
    ("English (UK)", "en_GB", "en_US"),
    ("Chileno", "es_CL", "es_CL"),
    ("Latino", "es_MX", "es_MX"),
    ("Español", "es_ES", "es_ES"),
    ("Deutsch", "de_DE", "de_DE"),
    ("Österreichisch", "de_AT", "de_DE"),
    ("Français", "fr_FR", "fr_FR"),
    ("Québécois", "fr_CA", "fr_FR"),
    ("Português (Brasil)", "pt_BR", "pt_BR"),
    ("Português (Portugal)", "pt_PT", "pt_BR"),
    ("Italiano", "it_IT", "it_IT"),
    ("Nederlands", "nl_NL", "nl_NL"),
    ("Polski", "pl_PL", "pl_PL"),
    ("Русский", "ru_RU", "ru_RU"),
    ("中文 (简体)", "zh_CN", "zh_CN"),
    ("中文 (繁體)", "zh_TW", "zh_CN"),
    ("日本語", "ja_JP", "ja_JP"),
    ("Türkçe", "tr_TR", "tr_TR"),
]

# ---------------------------------------------------------------------------
# TUIBuffer
# ---------------------------------------------------------------------------


@dataclass
class TUIBuffer:
    """All installer values pre-filled by the two-panel menu."""

    # Locale
    locale: str = "en_US.UTF-8"
    keymap: str = "us"
    timezone: str = "UTC"
    # System
    hostname: str = ""
    # Users (list of dicts matching show_users_creation() contract)
    users: list[dict] = field(default_factory=list)
    shell: str = "bash"
    # Desktop
    desktop_profile: str = "minimal"
    desktop_dm: str = "none"
    gpu_driver: str = "auto"
    # Security
    secure_boot: bool = False
    tpm2_unlock: bool = False
    fido2_pam: bool = False
    # Disk
    disk_device: str = ""
    use_luks: bool = False
    luks_passphrase: str = ""
    # Network
    wifi_ssid: str = ""
    wifi_passphrase: str = ""
    enable_ssh: bool = False
    # Install progress tracking
    phase: str = ""
    phase_progress: dict[str, float] = field(default_factory=dict)
    install_log: list[str] = field(default_factory=list)
    install_done: bool = False
    install_error: str = ""


# ---------------------------------------------------------------------------
# Textual availability guard
# ---------------------------------------------------------------------------

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer
    from textual.css.query import NoMatches
    from textual.screen import Screen
    from textual.widgets import (
        Button,
        ContentSwitcher,
        Footer,
        Input,
        Label,
        ListItem,
        ListView,
        Static,
    )

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


# ---------------------------------------------------------------------------
# Disk detection helper
# ---------------------------------------------------------------------------


def _lsblk_disks() -> list[dict[str, str]]:
    """Return list of block devices suitable for installation."""
    import json

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


# ---------------------------------------------------------------------------
# Textual widgets (only defined when textual is available)
# ---------------------------------------------------------------------------

if HAS_TEXTUAL:

    class GradientBar(Static):
        """Horizontal progress bar with a green gradient fill.

        Fills left to right. Leading edge (right side of fill) is bright
        (#00FF66), trailing side is dark (#067B3B). Empty chars use ░.
        """

        DEFAULT_CSS = """
        GradientBar {
            height: 1;
            width: 100%;
        }
        """

        def __init__(self, label: str = "", percent: float = 0.0, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._label = label
            self._percent = percent

        def render(self) -> str:  # type: ignore[override]
            width = self.size.width or 40
            label_part = f" {self._label}: " if self._label else " "
            pct_part = f" {int(self._percent):>3}%"
            bar_width = max(4, width - len(label_part) - len(pct_part))
            filled = int(self._percent / 100 * bar_width)
            empty = bar_width - filled

            bar_chars = "█" * filled + "░" * empty
            return f"{label_part}{bar_chars}{pct_part}"

        def update_percent(self, percent: float) -> None:
            """Update the displayed percentage and refresh."""
            self._percent = max(0.0, min(100.0, percent))
            self.refresh()

    class LogoWidget(Static):
        """Displays the ouroborOS ASCII logo on a dark green background."""

        DEFAULT_CSS = """
        LogoWidget {
            background: #083F28;
            color: #00FF66;
            height: auto;
            width: 100%;
            padding: 0;
        }
        """

        def render(self) -> str:  # type: ignore[override]
            return LOGO

    class ProgressPane(Static):
        """Installation progress pane with four phase bars plus an overall bar."""

        DEFAULT_CSS = """
        ProgressPane {
            padding: 1 2;
        }
        """

        def compose(self) -> ComposeResult:
            yield Label("Installation Progress", classes="section-title")
            yield Label("")
            yield Label("FORMAT (10%)", classes="dim")
            yield GradientBar(label="FORMAT", percent=0.0, id="bar-format")
            yield Label("")
            yield Label("INSTALL (50%)", classes="dim")
            yield GradientBar(label="INSTALL", percent=0.0, id="bar-install")
            yield Label("")
            yield Label("CONFIGURE (35%)", classes="dim")
            yield GradientBar(label="CONFIGURE", percent=0.0, id="bar-configure")
            yield Label("")
            yield Label("SNAPSHOT (5%)", classes="dim")
            yield GradientBar(label="SNAPSHOT", percent=0.0, id="bar-snapshot")
            yield Label("")
            yield Label("Overall", classes="section-title")
            yield GradientBar(label="Overall", percent=0.0, id="bar-overall")

        def update_phase(self, phase: str, pct: float) -> None:
            """Update one of the phase progress bars."""
            bar_id = f"bar-{phase.lower()}"
            try:
                bar = self.query_one(f"#{bar_id}", GradientBar)
                bar.update_percent(pct)
            except NoMatches:
                pass
            self._recalculate_overall()

        def _recalculate_overall(self) -> None:
            """Weighted average across the four phases."""
            weights = {"format": 0.10, "install": 0.50, "configure": 0.35, "snapshot": 0.05}
            total = 0.0
            for phase, weight in weights.items():
                bar_id = f"bar-{phase}"
                try:
                    bar = self.query_one(f"#{bar_id}", GradientBar)
                    total += bar._percent * weight
                except NoMatches:
                    pass
            try:
                overall = self.query_one("#bar-overall", GradientBar)
                overall.update_percent(total)
            except NoMatches:
                pass

    class DonePane(Static):
        """Post-install completion pane with reboot/shutdown/exit buttons."""

        DEFAULT_CSS = """
        DonePane {
            padding: 1 2;
        }
        """

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("Installation Complete!", classes="success")
            yield Label("")

            profile = self._buffer.desktop_profile or "minimal"
            hostname = self._buffer.hostname or "(not set)"
            locale = self._buffer.locale
            disk = self._buffer.disk_device or "(not set)"

            yield Label(f"Desktop profile : {profile}", classes="value")
            yield Label(f"Hostname        : {hostname}", classes="value")
            yield Label(f"Locale          : {locale}", classes="value")
            yield Label(f"Disk            : {disk}", classes="value")
            yield Label("")
            yield Label("What would you like to do?", classes="section-title")
            yield Label("")
            with Horizontal():
                yield Button("Reboot", id="btn-reboot", classes="primary")
                yield Button("Shutdown", id="btn-shutdown")
                yield Button("Exit to shell", id="btn-exit")

        @on(Button.Pressed, "#btn-reboot")
        def _reboot(self) -> None:
            self._q.put("reboot")

        @on(Button.Pressed, "#btn-shutdown")
        def _shutdown(self) -> None:
            self._q.put("shutdown")

        @on(Button.Pressed, "#btn-exit")
        def _exit_shell(self) -> None:
            self._q.put("none")

    # ---------------------------------------------------------------------------
    # Simple modal-style edit panes (one per category)
    # ---------------------------------------------------------------------------

    class LocalePane(Static):
        """Edit pane for locale/keymap/timezone configuration."""

        DEFAULT_CSS = "LocalePane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("Localization", classes="section-title")
            yield Label("")
            yield Label("Locale (e.g. en_US.UTF-8):")
            yield Input(value=self._buffer.locale, id="input-locale")
            yield Label("")
            yield Label("Keymap (e.g. us, de, es):")
            yield Input(value=self._buffer.keymap, id="input-keymap")
            yield Label("")
            yield Label("Timezone (e.g. UTC, America/New_York):")
            yield Input(value=self._buffer.timezone, id="input-timezone")
            yield Label("")
            yield Button("Apply", id="btn-locale-apply", classes="primary")

        @on(Button.Pressed, "#btn-locale-apply")
        def _apply(self) -> None:
            try:
                locale_val = self.query_one("#input-locale", Input).value.strip() or "en_US.UTF-8"
                keymap_val = self.query_one("#input-keymap", Input).value.strip() or "us"
                tz_val = self.query_one("#input-timezone", Input).value.strip() or "UTC"
            except NoMatches:
                return
            self._buffer.locale = locale_val
            self._buffer.keymap = keymap_val
            self._buffer.timezone = tz_val
            self._q.put({"locale": locale_val, "keymap": keymap_val, "timezone": tz_val})

    class HostnamePane(Static):
        """Edit pane for hostname configuration."""

        DEFAULT_CSS = "HostnamePane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("Hostname", classes="section-title")
            yield Label("")
            yield Label("Enter a hostname for the installed system:")
            yield Input(value=self._buffer.hostname or "ouroboros", id="input-hostname")
            yield Label("")
            yield Button("Apply", id="btn-hostname-apply", classes="primary")

        @on(Button.Pressed, "#btn-hostname-apply")
        def _apply(self) -> None:
            try:
                hostname_val = self.query_one("#input-hostname", Input).value.strip() or "ouroboros"
            except NoMatches:
                return
            self._buffer.hostname = hostname_val
            self._q.put(hostname_val)

    class UsersPane(Static):
        """Edit pane for single-user creation (primary user)."""

        DEFAULT_CSS = "UsersPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("User & Authentication", classes="section-title")
            yield Label("")
            yield Label("Username:")
            default_user = self._buffer.users[0]["username"] if self._buffer.users else "user"
            yield Input(value=default_user, id="input-username")
            yield Label("")
            yield Label("Password:")
            yield Input(value="", id="input-password", password=True)
            yield Label("")
            yield Label("Confirm password:")
            yield Input(value="", id="input-password-confirm", password=True)
            yield Label("")
            yield Label("Home storage (subvolume/directory/luks/classic):")
            yield Input(value="subvolume", id="input-homed-storage")
            yield Label("")
            yield Button("Apply", id="btn-users-apply", classes="primary")
            yield Label("", id="users-error", classes="error")

        @on(Button.Pressed, "#btn-users-apply")
        def _apply(self) -> None:
            try:
                username = self.query_one("#input-username", Input).value.strip() or "user"
                password = self.query_one("#input-password", Input).value
                confirm = self.query_one("#input-password-confirm", Input).value
                homed = self.query_one("#input-homed-storage", Input).value.strip() or "subvolume"
                error_label = self.query_one("#users-error", Label)
            except NoMatches:
                return

            if password != confirm:
                error_label.update("Passwords do not match.")
                return
            if len(password) < 4:
                error_label.update("Password must be at least 4 characters.")
                return

            import os as _os
            import subprocess as _sp
            salt = _os.urandom(16).hex()[:16]
            try:
                result = _sp.run(
                    ["openssl", "passwd", "-6", "-salt", salt, password],
                    capture_output=True, text=True, check=True,
                )
                password_hash = result.stdout.strip()
            except Exception:
                password_hash = ""

            user_dict = {
                "username": username,
                "password": password,
                "password_hash": password_hash,
                "homed_storage": homed,
                "groups": ["wheel", "audio", "video", "input"],
            }
            self._buffer.users = [user_dict]
            error_label.update("")
            self._q.put([user_dict])

    class ShellPane(Static):
        """Edit pane for login shell selection."""

        DEFAULT_CSS = "ShellPane { padding: 1 2; }"

        _SHELLS = [
            ("bash", "Bash — POSIX-compatible, universal default"),
            ("zsh", "Zsh — advanced completion"),
            ("fish", "Fish — modern and user-friendly"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("Login Shell", classes="section-title")
            yield Label("")
            for shell, desc in self._SHELLS:
                selected = " (selected)" if shell == self._buffer.shell else ""
                yield Button(f"{shell} — {desc}{selected}", id=f"btn-shell-{shell}")

        @on(Button.Pressed)
        def _pick(self, event: Button.Pressed) -> None:
            btn_id = event.button.id or ""
            if btn_id.startswith("btn-shell-"):
                shell = btn_id[len("btn-shell-"):]
                self._buffer.shell = shell
                self._q.put(shell)

    class DesktopPane(Static):
        """Edit pane for desktop profile and DM selection."""

        DEFAULT_CSS = "DesktopPane { padding: 1 2; }"

        _PROFILES = [
            ("minimal", "Nothing extra — TTY only"),
            ("hyprland", "Hyprland + Hypr ecosystem"),
            ("niri", "Niri + foot + fuzzel"),
            ("gnome", "GNOME desktop"),
            ("kde", "KDE Plasma"),
            ("cosmic", "COSMIC Desktop"),
        ]
        _DMS = [
            ("auto", "Recommended"),
            ("gdm", "GDM"),
            ("sddm", "SDDM"),
            ("plm", "PLM"),
            ("greetd", "greetd"),
            ("none", "TTY login"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue
            self._waiting_for: str = "profile"

        def compose(self) -> ComposeResult:
            yield Label("Desktop Environment", classes="section-title")
            yield Label("")
            yield Label("Desktop profile:", classes="dim")
            for key, desc in self._PROFILES:
                selected = " [current]" if key == self._buffer.desktop_profile else ""
                yield Button(f"{key}: {desc}{selected}", id=f"btn-profile-{key}")
            yield Label("")
            yield Label("Display manager:", classes="dim")
            for key, desc in self._DMS:
                selected = " [current]" if key == self._buffer.desktop_dm else ""
                yield Button(f"{key}: {desc}{selected}", id=f"btn-dm-{key}")

        @on(Button.Pressed)
        def _pick(self, event: Button.Pressed) -> None:
            btn_id = event.button.id or ""
            if btn_id.startswith("btn-profile-"):
                profile = btn_id[len("btn-profile-"):]
                self._buffer.desktop_profile = profile
                if self._waiting_for == "profile":
                    self._q.put(profile)
            elif btn_id.startswith("btn-dm-"):
                dm = btn_id[len("btn-dm-"):]
                self._buffer.desktop_dm = dm
                if self._waiting_for == "dm":
                    self._q.put(dm)

    class GpuPane(Static):
        """Edit pane for GPU driver selection."""

        DEFAULT_CSS = "GpuPane { padding: 1 2; }"

        _OPTIONS = [
            ("auto", "Auto-detect (default)"),
            ("mesa", "Mesa — Intel/AMD open source"),
            ("amdgpu", "AMD GPU explicit"),
            ("nvidia", "NVIDIA proprietary"),
            ("nvidia-open", "NVIDIA Open kernel module"),
            ("none", "Skip — install manually"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("GPU Drivers", classes="section-title")
            yield Label("")
            for key, desc in self._OPTIONS:
                selected = " [current]" if key == self._buffer.gpu_driver else ""
                yield Button(f"{key}: {desc}{selected}", id=f"btn-gpu-{key}")

        @on(Button.Pressed)
        def _pick(self, event: Button.Pressed) -> None:
            btn_id = event.button.id or ""
            if btn_id.startswith("btn-gpu-"):
                driver = btn_id[len("btn-gpu-"):]
                self._buffer.gpu_driver = driver
                self._q.put(driver)

    class DiskPane(Static):
        """Edit pane for disk selection."""

        DEFAULT_CSS = "DiskPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label("Disk Configuration", classes="section-title")
            yield Label("")
            disks = _lsblk_disks()
            if disks:
                yield Label("Select target disk:", classes="dim")
                for disk in disks:
                    label = f"{disk['name']}  {disk['size']:>8}  {disk['model'][:30]}"
                    yield Button(label, id=f"btn-disk-{disk['name'].replace('/', '_')}")
            else:
                yield Label("No disks found. Enter path manually:", classes="warning")
            yield Label("")
            yield Label("Or enter device path manually:")
            yield Input(value=self._buffer.disk_device, id="input-disk-manual")
            yield Button("Use manual path", id="btn-disk-manual", classes="primary")

        @on(Button.Pressed)
        def _pick(self, event: Button.Pressed) -> None:
            btn_id = event.button.id or ""
            if btn_id.startswith("btn-disk-/"):
                # Reconstruct device path from button id
                device = btn_id[len("btn-disk-"):].replace("_dev_", "/dev/")
                self._buffer.disk_device = device
                self._q.put(device)
            elif btn_id == "btn-disk-manual":
                try:
                    manual = self.query_one("#input-disk-manual", Input).value.strip()
                except NoMatches:
                    return
                if manual:
                    self._buffer.disk_device = manual
                    self._q.put(manual)

    class EncryptionPane(Static):
        """Edit pane for LUKS disk encryption settings."""

        DEFAULT_CSS = "EncryptionPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue
            self._waiting_for: str = "passphrase"

        def compose(self) -> ComposeResult:
            yield Label("Disk Encryption", classes="section-title")
            yield Label("")
            yield Label("LUKS2 passphrase:")
            yield Input(value="", id="input-luks-pass", password=True)
            yield Label("Confirm passphrase:")
            yield Input(value="", id="input-luks-confirm", password=True)
            yield Label("")
            yield Button("Set passphrase", id="btn-luks-apply", classes="primary")
            yield Label("", id="luks-error", classes="error")

        @on(Button.Pressed, "#btn-luks-apply")
        def _apply(self) -> None:
            try:
                passphrase = self.query_one("#input-luks-pass", Input).value
                confirm = self.query_one("#input-luks-confirm", Input).value
                error_label = self.query_one("#luks-error", Label)
            except NoMatches:
                return
            if passphrase != confirm:
                error_label.update("Passphrases do not match.")
                return
            if len(passphrase) < 4:
                error_label.update("Passphrase must be at least 4 characters.")
                return
            self._buffer.luks_passphrase = passphrase
            error_label.update("")
            self._q.put(passphrase)

    class SecurityPane(Static):
        """Edit pane for Secure Boot, TPM2, and FIDO2 settings."""

        DEFAULT_CSS = "SecurityPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue
            self._waiting_for: str = "secure_boot"

        def compose(self) -> ComposeResult:
            tpm_available = os.path.exists("/sys/class/tpm/tpm0")
            tpm_note = "" if tpm_available else " (no TPM2 detected)"

            yield Label("Security", classes="section-title")
            yield Label("")
            yield Label("Secure Boot (requires UEFI Setup Mode):")
            yield Button("Enable Secure Boot", id="btn-sb-enable", classes="primary")
            yield Button("Disable Secure Boot", id="btn-sb-disable")
            yield Label("")
            yield Label(f"TPM2 auto-unlock for LUKS{tpm_note}:")
            yield Button("Enable TPM2", id="btn-tpm2-enable", classes="primary")
            yield Button("Disable TPM2", id="btn-tpm2-disable")
            yield Label("")
            yield Label("FIDO2 PAM authentication:")
            yield Button("Enable FIDO2", id="btn-fido2-enable", classes="primary")
            yield Button("Disable FIDO2", id="btn-fido2-disable")

        @on(Button.Pressed)
        def _pick(self, event: Button.Pressed) -> None:
            btn_id = event.button.id or ""
            mapping = {
                "btn-sb-enable": ("secure_boot", True),
                "btn-sb-disable": ("secure_boot", False),
                "btn-tpm2-enable": ("tpm2_unlock", True),
                "btn-tpm2-disable": ("tpm2_unlock", False),
                "btn-fido2-enable": ("fido2_pam", True),
                "btn-fido2-disable": ("fido2_pam", False),
            }
            if btn_id in mapping:
                attr, val = mapping[btn_id]
                setattr(self._buffer, attr, val)
                if self._waiting_for == attr:
                    self._q.put(val)

    class NetworkPane(Static):
        """Edit pane for WiFi SSID, passphrase, and SSH settings."""

        DEFAULT_CSS = "NetworkPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue
            self._waiting_for: str = "ssid"

        def compose(self) -> ComposeResult:
            yield Label("Network", classes="section-title")
            yield Label("")
            yield Label("WiFi SSID (leave blank to skip):")
            yield Input(value=self._buffer.wifi_ssid, id="input-wifi-ssid")
            yield Label("")
            yield Label("WiFi passphrase:")
            yield Input(value=self._buffer.wifi_passphrase, id="input-wifi-pass", password=True)
            yield Label("")
            yield Label("SSH:")
            yield Button("Enable SSH", id="btn-ssh-enable", classes="primary")
            yield Button("Disable SSH", id="btn-ssh-disable")
            yield Label("")
            yield Button("Apply network settings", id="btn-network-apply", classes="primary")

        @on(Button.Pressed, "#btn-network-apply")
        def _apply(self) -> None:
            try:
                ssid = self.query_one("#input-wifi-ssid", Input).value.strip()
                passphrase = self.query_one("#input-wifi-pass", Input).value
            except NoMatches:
                return
            self._buffer.wifi_ssid = ssid
            self._buffer.wifi_passphrase = passphrase
            if self._waiting_for == "ssid":
                self._q.put(ssid)
            elif self._waiting_for == "passphrase":
                self._q.put(passphrase)

        @on(Button.Pressed, "#btn-ssh-enable")
        def _ssh_enable(self) -> None:
            self._buffer.enable_ssh = True
            if self._waiting_for == "ssh":
                self._q.put(True)

        @on(Button.Pressed, "#btn-ssh-disable")
        def _ssh_disable(self) -> None:
            self._buffer.enable_ssh = False
            if self._waiting_for == "ssh":
                self._q.put(False)

    class PartitionPreviewPane(Static):
        """Shows the proposed partition layout for confirmation."""

        DEFAULT_CSS = "PartitionPreviewPane { padding: 1 2; }"

        def __init__(self, config: Any, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._config = config
            self._q = response_queue

        def compose(self) -> ComposeResult:
            cfg_disk = getattr(self._config, "disk", None)
            if isinstance(self._config, str):
                disk = self._config
                use_luks = False
            else:
                disk = getattr(cfg_disk, "device", str(self._config))
                use_luks = getattr(cfg_disk, "use_luks", False)
            luks_tag = " (LUKS2 encrypted)" if use_luks else ""

            yield Label("Partition Preview", classes="section-title")
            yield Label("")
            yield Label(f"Target disk: {disk}", classes="value")
            yield Label("")
            yield Label("Proposed layout:", classes="dim")
            yield Label("  Partition 1:  512 MiB   ESP (FAT32)")
            yield Label(f"  Partition 2:  remaining  Btrfs{luks_tag}")
            yield Label("")
            yield Label("Btrfs subvolumes:", classes="dim")
            yield Label("  @           ->  /           (read-only at boot)")
            yield Label("  @var        ->  /var")
            yield Label("  @etc        ->  /etc")
            yield Label("  @home       ->  /home")
            yield Label("  @snapshots  ->  /.snapshots")
            yield Label("  Swap: zram (no swap partition)")
            yield Label("")
            yield Label("WARNING: All data on the target disk will be ERASED.", classes="warning")
            yield Label("")
            with Horizontal():
                yield Button("Confirm — erase disk", id="btn-preview-confirm", classes="danger")
                yield Button("Abort", id="btn-preview-abort")

        @on(Button.Pressed, "#btn-preview-confirm")
        def _confirm(self) -> None:
            self._q.put(True)

        @on(Button.Pressed, "#btn-preview-abort")
        def _abort(self) -> None:
            self._q.put(False)

    class PreviewPane(Static):
        """Default right-panel content: shows current buffer summary."""

        DEFAULT_CSS = "PreviewPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer

        def compose(self) -> ComposeResult:
            yield Label("Installation Summary", classes="section-title")
            yield Label("")
            yield Label(f"Locale   : {self._buffer.locale}", classes="value")
            yield Label(f"Keymap   : {self._buffer.keymap}", classes="value")
            yield Label(f"Timezone : {self._buffer.timezone}", classes="value")
            yield Label(f"Hostname : {self._buffer.hostname or '(not set)'}", classes="dim")
            yield Label(f"Shell    : {self._buffer.shell}", classes="value")
            yield Label(f"Desktop  : {self._buffer.desktop_profile}", classes="value")
            yield Label(f"DM       : {self._buffer.desktop_dm}", classes="dim")
            yield Label(f"GPU      : {self._buffer.gpu_driver}", classes="dim")
            yield Label(f"Disk     : {self._buffer.disk_device or '(not set)'}", classes="dim")
            yield Label(f"LUKS     : {'Yes' if self._buffer.use_luks else 'No'}", classes="dim")
            yield Label("")
            yield Label("Select a category from the left panel.", classes="dim")

    # ---------------------------------------------------------------------------
    # Screens
    # ---------------------------------------------------------------------------

    class LanguageScreen(Screen):  # type: ignore[misc]
        """Full-screen language selection — shown before i18n is initialised."""

        BINDINGS = [Binding("escape", "app.quit", "Quit")]

        def __init__(self, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield LogoWidget()
            yield Label("")
            yield Label("Select installer language / Seleccione idioma / Sprache wählen", classes="section-title")
            yield Label("")
            yield ListView(
                *[ListItem(Label(display), id=f"lang-{i}") for i, (display, _, _) in enumerate(LOCALE_CATALOG)],
                id="language-list",
            )
            yield Footer()

        @on(ListView.Selected)
        def _selected(self, event: ListView.Selected) -> None:
            item_id = event.item.id or "lang-0"
            try:
                idx = int(item_id.split("-")[1])
            except (ValueError, IndexError):
                idx = 0
            _display, locale_code, i18n_code = LOCALE_CATALOG[idx]
            init_i18n(i18n_code)
            self._q.put(locale_code)
            self.app.push_screen(MainMenuScreen(self.app._buffer, self.app._response_queue))  # type: ignore[attr-defined]

    class MainMenuScreen(Screen):  # type: ignore[misc]
        """Two-panel main menu screen."""

        BINDINGS = [
            Binding("escape", "app.quit", "Abort"),
            Binding("q", "app.quit", "Quit"),
        ]

        _MENU_ITEMS = [
            ("localization", "Localization"),
            ("disk", "Disk configuration"),
            ("encryption", "Disk encryption"),
            ("hostname", "Hostname"),
            ("users", "Users & Authentication"),
            ("shell", "Shell"),
            ("desktop", "Desktop environment"),
            ("gpu", "GPU drivers"),
            ("security", "Security"),
            ("network", "Network"),
            ("separator", "───────────────────"),
            ("install", "Install"),
            ("abort", "Abort"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield LogoWidget()
            with Horizontal():
                with ScrollableContainer(id="left-panel"):
                    yield ListView(
                        *[
                            ListItem(Label(label), id=f"menu-{key}")
                            for key, label in self._MENU_ITEMS
                        ],
                        id="main-menu",
                    )
                with ScrollableContainer(id="right-panel"):
                    with ContentSwitcher(initial="pane-preview"):
                        yield PreviewPane(self._buffer, id="pane-preview")
                        yield LocalePane(self._buffer, self._q, id="pane-localization")
                        yield DiskPane(self._buffer, self._q, id="pane-disk")
                        yield EncryptionPane(self._buffer, self._q, id="pane-encryption")
                        yield HostnamePane(self._buffer, self._q, id="pane-hostname")
                        yield UsersPane(self._buffer, self._q, id="pane-users")
                        yield ShellPane(self._buffer, self._q, id="pane-shell")
                        yield DesktopPane(self._buffer, self._q, id="pane-desktop")
                        yield GpuPane(self._buffer, self._q, id="pane-gpu")
                        yield SecurityPane(self._buffer, self._q, id="pane-security")
                        yield NetworkPane(self._buffer, self._q, id="pane-network")
                        yield ProgressPane(id="pane-progress")
                        yield DonePane(self._buffer, self._q, id="pane-done")
            yield Footer()

        @on(ListView.Selected)
        def _menu_selected(self, event: ListView.Selected) -> None:
            item_id = event.item.id or ""
            if item_id == "menu-separator":
                return
            if item_id == "menu-abort":
                self.app.exit(1)
                return
            if item_id == "menu-install":
                self._start_install()
                return

            category = item_id[len("menu-"):]
            pane_id = f"pane-{category}"
            try:
                switcher = self.query_one(ContentSwitcher)
                switcher.current = pane_id
            except NoMatches:
                pass

        def _start_install(self) -> None:
            """Switch to progress pane and signal FSM to begin installation."""
            try:
                switcher = self.query_one(ContentSwitcher)
                switcher.current = "pane-progress"
            except NoMatches:
                pass
            self._q.put("_install_start")

        def show_done(self) -> None:
            """Switch to the DonePane after installation completes."""
            try:
                switcher = self.query_one(ContentSwitcher)
                switcher.current = "pane-done"
            except NoMatches:
                pass

        def update_progress(self, phase: str, pct: float) -> None:
            """Update a progress bar (called from FSM worker thread via call_from_thread)."""
            try:
                pane = self.query_one("#pane-progress", ProgressPane)
                pane.update_phase(phase, pct)
            except NoMatches:
                pass

    # ---------------------------------------------------------------------------
    # Main Textual app
    # ---------------------------------------------------------------------------

    class InstallerApp(App):  # type: ignore[misc]
        """ouroborOS Textual installer application."""

        CSS_PATH = None  # CSS loaded inline via DEFAULT_CSS
        TITLE = "ouroborOS Installer"
        SUB_TITLE = "v0.6.0"
        BINDINGS = [Binding("ctrl+c", "quit", "Quit")]

        DEFAULT_CSS = """
Screen { background: #000000; color: #ffffff; }
LogoWidget { background: #083F28; color: #00FF66; height: auto; width: 100%; padding: 0; }
#left-panel { width: 35%; border-right: tall #419E6E; }
#right-panel { width: 65%; padding: 0 1; }
ListView > ListItem.--highlight { background: #00FF66; color: #000000; }
ListView > ListItem { padding: 0 1; }
.section-title { color: #419E6E; text-style: bold; }
.value { color: #00FF66; }
.dim { color: #555555; }
.warning { color: #f4a261; }
.error { color: #d62828; }
.success { color: #00FF66; text-style: bold; }
Button.primary { background: #067B3B; color: #ffffff; }
Button.danger { background: #d62828; color: #ffffff; }
GradientBar { height: 1; width: 100%; }
ProgressPane { padding: 1 2; }
#language-screen { align: center middle; }
#language-list { width: 50; }
"""

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = TUIBuffer()
            self._response_queue: queue.Queue[Any] = queue.Queue()
            self._lang_queue: queue.Queue[Any] = queue.Queue()

        def on_mount(self) -> None:
            self.push_screen(LanguageScreen(self._response_queue))

        def update_progress(self, phase: str, pct: float) -> None:
            """Update progress bar from FSM worker thread."""
            try:
                screen = self.screen
                if hasattr(screen, "update_progress"):
                    screen.update_progress(phase, pct)  # type: ignore[attr-defined]
            except Exception:
                pass

        def show_done_screen(self) -> None:
            """Switch to done pane after installation completes."""
            try:
                screen = self.screen
                if hasattr(screen, "show_done"):
                    screen.show_done()  # type: ignore[attr-defined]
            except Exception:
                pass


# ---------------------------------------------------------------------------
# TUI adapter class — implements the 25 show_* methods
# ---------------------------------------------------------------------------


class TUI:
    """Textual-backed installer TUI.

    Implements the 25 show_* interface methods used by the ouroborOS installer.
    Each method either reads from TUIBuffer (if already filled by the menu) or
    blocks on response_queue waiting for the user to interact with the
    corresponding pane.

    Falls back to the Rich-based TUI if Textual is not installed.
    """

    def __init__(self, title: str = "ouroborOS Installer") -> None:
        self._title = title
        if not HAS_TEXTUAL:
            # Lazy import of Rich fallback
            from installer.tui import TUI as _RichTUI  # type: ignore[import]
            self._rich = _RichTUI(title=title)
            self._app: InstallerApp | None = None
            self._q: queue.Queue[Any] | None = None
            return

        self._rich = None
        self._app = InstallerApp()
        self._q = self._app._response_queue
        self._buffer = self._app._buffer

        # Start Textual app in a background thread so the FSM can block on queue
        self._app_thread = threading.Thread(target=self._run_app, daemon=True)
        self._app_thread.start()

    def _run_app(self) -> None:
        """Run the Textual app in its own thread.

        Python's signal.signal() only works on the main thread. Textual's
        LinuxDriver sets SIGTSTP/SIGCONT handlers for Ctrl+Z support. Since
        we run Textual in a background thread (main thread runs the FSM), we
        patch signal.signal to silently skip those registrations. Ctrl+Z
        suspend is irrelevant in an installer context.
        """
        import signal as _signal_mod

        _orig_signal = _signal_mod.signal

        def _thread_safe_signal(sig: Any, handler: Any) -> Any:
            try:
                return _orig_signal(sig, handler)
            except ValueError:
                return None  # not in main thread — skip

        _signal_mod.signal = _thread_safe_signal  # type: ignore[assignment]
        try:
            self._app.run()  # type: ignore[union-attr]
        finally:
            _signal_mod.signal = _orig_signal  # type: ignore[assignment]

    def _get(self) -> Any:
        """Block until a value is available on the response queue."""
        assert self._q is not None
        return self._q.get()

    def _delegate(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Forward a call to the Rich fallback TUI."""
        return getattr(self._rich, method_name)(*args, **kwargs)

    # ------------------------------------------------------------------
    # 1. show_locale_menu
    # ------------------------------------------------------------------

    def show_locale_menu(self) -> dict[str, str]:
        """Return locale, keymap, and timezone dict."""
        if self._rich:
            return self._delegate("show_locale_menu")
        val = self._get()
        if isinstance(val, dict) and "locale" in val:
            return val
        return {"locale": self._buffer.locale, "keymap": self._buffer.keymap, "timezone": self._buffer.timezone}

    # ------------------------------------------------------------------
    # 2. show_hostname_input
    # ------------------------------------------------------------------

    def show_hostname_input(self) -> str:
        """Return hostname string."""
        if self._rich:
            return self._delegate("show_hostname_input")
        if self._buffer.hostname:
            return self._buffer.hostname
        val = self._get()
        return str(val) if val else "ouroboros"

    # ------------------------------------------------------------------
    # 3. show_users_creation
    # ------------------------------------------------------------------

    def show_users_creation(self) -> list[dict]:
        """Return list of user configuration dicts."""
        if self._rich:
            return self._delegate("show_users_creation")
        if self._buffer.users:
            return list(self._buffer.users)
        val = self._get()
        return val if isinstance(val, list) else [val]

    # ------------------------------------------------------------------
    # 4. show_shell_selection
    # ------------------------------------------------------------------

    def show_shell_selection(self) -> str:
        """Return shell name (bash/zsh/fish)."""
        if self._rich:
            return self._delegate("show_shell_selection")
        if self._buffer.shell and self._buffer.shell != "bash":
            return self._buffer.shell
        val = self._get()
        return str(val) if val else "bash"

    # ------------------------------------------------------------------
    # 5. show_desktop_profile
    # ------------------------------------------------------------------

    def show_desktop_profile(self) -> str:
        """Return desktop profile name."""
        if self._rich:
            return self._delegate("show_desktop_selection")
        val = self._get()
        return str(val) if val else "minimal"

    # ------------------------------------------------------------------
    # 6. show_desktop_dm
    # ------------------------------------------------------------------

    def show_desktop_dm(self, profile: str = "") -> str:
        """Return display manager name."""
        if self._rich:
            return self._delegate("show_dm_selection", profile=profile)
        if self._buffer.desktop_dm:
            return self._buffer.desktop_dm
        val = self._get()
        return str(val) if val else "none"

    # ------------------------------------------------------------------
    # 7. show_gpu_driver
    # ------------------------------------------------------------------

    def show_gpu_driver(self) -> str:
        """Return GPU driver choice."""
        if self._rich:
            return self._delegate("show_gpu_selection")
        val = self._get()
        return str(val) if val else "auto"

    # ------------------------------------------------------------------
    # 8. show_secure_boot
    # ------------------------------------------------------------------

    def show_secure_boot(self) -> bool:
        """Return True if Secure Boot should be enabled."""
        if self._rich:
            # Rich TUI shows an informational prompt (no bool return)
            self._delegate("show_secure_boot_prompt")
            return False
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 9. show_tpm2_unlock
    # ------------------------------------------------------------------

    def show_tpm2_unlock(self) -> bool:
        """Return True if TPM2 auto-unlock should be enabled."""
        if self._rich:
            return self._delegate("show_tpm2_prompt")
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 10. show_fido2_pam
    # ------------------------------------------------------------------

    def show_fido2_pam(self) -> bool:
        """Return True if FIDO2 PAM should be enabled."""
        if self._rich:
            return False  # Rich TUI has no FIDO2 screen
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 11. show_disk_selection
    # ------------------------------------------------------------------

    def show_disk_selection(self) -> str:
        """Return device path string."""
        if self._rich:
            return self._delegate("show_disk_selection")
        if self._buffer.disk_device:
            return self._buffer.disk_device
        val = self._get()
        return str(val) if val else ""

    # ------------------------------------------------------------------
    # 12. show_luks_passphrase
    # ------------------------------------------------------------------

    def show_luks_passphrase(self) -> str:
        """Return LUKS passphrase."""
        if self._rich:
            return self._delegate("show_passphrase_input")
        if self._buffer.luks_passphrase:
            return self._buffer.luks_passphrase
        val = self._get()
        return str(val) if val else ""

    # ------------------------------------------------------------------
    # 13. show_luks_confirmation
    # ------------------------------------------------------------------

    def show_luks_confirmation(self, passphrase: str) -> str:
        """Return confirmed LUKS passphrase."""
        if self._rich:
            return passphrase  # Rich handles confirm inside show_passphrase_input
        return passphrase  # Buffer already confirmed via EncryptionPane

    # ------------------------------------------------------------------
    # 14. show_wifi_ssid
    # ------------------------------------------------------------------

    def show_wifi_ssid(self) -> str:
        """Return WiFi SSID."""
        if self._rich:
            creds = self._delegate("show_wifi_connect")
            if creds and isinstance(creds, dict):
                return creds.get("ssid", "")
            return ""
        if self._buffer.wifi_ssid:
            return self._buffer.wifi_ssid
        val = self._get()
        return str(val) if val else ""

    # ------------------------------------------------------------------
    # 15. show_wifi_passphrase
    # ------------------------------------------------------------------

    def show_wifi_passphrase(self, ssid: str) -> str:
        """Return WiFi passphrase for the given SSID."""
        if self._rich:
            return ""  # Rich handles passphrase inside show_wifi_connect
        if self._buffer.wifi_passphrase:
            return self._buffer.wifi_passphrase
        val = self._get()
        return str(val) if val else ""

    # ------------------------------------------------------------------
    # 16. show_ssh_enable
    # ------------------------------------------------------------------

    def show_ssh_enable(self) -> bool:
        """Return True if SSH should be enabled."""
        if self._rich:
            return False  # Rich TUI has no SSH screen
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 17. show_partition_preview
    # ------------------------------------------------------------------

    def show_partition_preview(self, config: Any) -> bool:
        """Show partition layout. Returns True to confirm, False to abort."""
        if self._rich:
            # Rich version takes (disk, use_luks) and returns None
            disk = getattr(getattr(config, "disk", None), "device", str(config))
            use_luks = getattr(getattr(config, "disk", None), "use_luks", False)
            self._delegate("show_partition_preview", disk, use_luks)
            return True
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 18. show_install_progress
    # ------------------------------------------------------------------

    def show_install_progress(self, phase: str, pct: int, msg: str) -> None:
        """Update install progress display."""
        if self._rich:
            self._delegate("show_progress", phase, msg, pct)
            return
        if self._app is not None:
            self._app.call_from_thread(self._app.update_progress, phase.lower(), float(pct))

    # ------------------------------------------------------------------
    # 19. show_install_complete
    # ------------------------------------------------------------------

    def show_install_complete(self) -> None:
        """Show installation complete screen."""
        if self._rich:
            return
        if self._app is not None:
            self._app.call_from_thread(self._app.show_done_screen)

    # ------------------------------------------------------------------
    # 20. show_install_error
    # ------------------------------------------------------------------

    def show_install_error(self, error: str) -> None:
        """Show installation error."""
        if self._rich:
            self._delegate("show_error", error, False)

    # ------------------------------------------------------------------
    # 21. show_bluetooth_enable
    # ------------------------------------------------------------------

    def show_bluetooth_enable(self) -> bool:
        """Return True if Bluetooth should be enabled."""
        if self._rich:
            return False  # Rich TUI has no Bluetooth screen
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 22. show_reboot_prompt
    # ------------------------------------------------------------------

    def show_reboot_prompt(self) -> str:
        """Return 'reboot', 'shutdown', or 'none'."""
        if self._rich:
            return self._delegate("show_post_install_action")
        val = self._get()
        return str(val) if val in ("reboot", "shutdown", "none") else "reboot"

    # ------------------------------------------------------------------
    # 23. show_kde_flavor
    # ------------------------------------------------------------------

    def show_kde_flavor(self) -> str:
        """Return KDE Plasma flavor (plasma-meta/plasma/plasma-desktop)."""
        if self._rich:
            return self._delegate("show_kde_flavor")
        val = self._get()
        return str(val) if val else "plasma-meta"

    # ------------------------------------------------------------------
    # 24. show_dual_boot_enable
    # ------------------------------------------------------------------

    def show_dual_boot_enable(self) -> bool:
        """Return True if dual-boot support should be enabled."""
        if self._rich:
            return self._delegate("show_dual_boot_prompt", [])
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # 25. show_sbctl_ms_keys
    # ------------------------------------------------------------------

    def show_sbctl_ms_keys(self) -> bool:
        """Return True if Microsoft OEM keys should be enrolled in sbctl."""
        if self._rich:
            return False  # Rich TUI has no sbctl_ms_keys screen
        val = self._get()
        return bool(val)

    # ------------------------------------------------------------------
    # Legacy compatibility methods (used by state_machine.py)
    # ------------------------------------------------------------------

    def show_language_selection(self) -> str:
        """Legacy: return language code for i18n init."""
        if self._rich:
            return self._delegate("show_language_selection")
        val = self._get()
        return str(val) if val else "en_US"

    def show_welcome(self) -> None:
        """Legacy: show welcome screen (no-op in Textual — menu is always visible)."""
        if self._rich:
            self._delegate("show_welcome")

    def show_remote_config_prompt(self) -> str | None:
        """Legacy: ask for a remote config URL."""
        if self._rich:
            return self._delegate("show_remote_config_prompt")
        return None

    def show_error(self, message: str, recoverable: bool = True) -> bool:
        """Legacy: show error message."""
        if self._rich:
            return self._delegate("show_error", message, recoverable)
        return False

    def show_confirmation(self, message: str) -> bool:
        """Legacy: show confirmation dialog."""
        if self._rich:
            return self._delegate("show_confirmation", message)
        val = self._get()
        return bool(val)

    def show_wifi_connect(self) -> dict | None:
        """Legacy: WiFi connect flow."""
        if self._rich:
            return self._delegate("show_wifi_connect")
        return None

    def show_desktop_selection(self) -> str:
        """Legacy alias for show_desktop_profile."""
        return self.show_desktop_profile()

    def show_dm_selection(self, profile: str = "") -> str:
        """Legacy alias for show_desktop_dm."""
        return self.show_desktop_dm(profile=profile)

    def show_gpu_selection(self, detected: str = "auto") -> str:
        """Legacy alias for show_gpu_driver."""
        return self.show_gpu_driver()

    def show_luks_prompt(self) -> bool:
        """Legacy: ask whether to enable LUKS."""
        if self._rich:
            return self._delegate("show_luks_prompt")
        return self._buffer.use_luks

    def show_passphrase_input(self) -> str:
        """Legacy alias for show_luks_passphrase."""
        return self.show_luks_passphrase()

    def show_tpm2_prompt(self) -> bool:
        """Legacy alias for show_tpm2_unlock."""
        return self.show_tpm2_unlock()

    def show_dual_boot_prompt(self, detected_os: list[str]) -> bool:
        """Legacy alias for show_dual_boot_enable."""
        if self._rich:
            return self._delegate("show_dual_boot_prompt", detected_os)
        return self.show_dual_boot_enable()

    def show_secure_boot_prompt(self) -> None:
        """Legacy: show Secure Boot instructions (informational)."""
        self.show_secure_boot()

    def show_summary(self, config: Any) -> None:
        """Legacy: show installation summary."""
        if self._rich:
            self._delegate("show_summary", config)

    def show_post_install_action(self) -> str:
        """Legacy alias for show_reboot_prompt."""
        return self.show_reboot_prompt()

    def start_install_progress(self) -> None:
        """Legacy: start global progress bar."""
        if self._rich:
            self._delegate("start_install_progress")

    def stop_install_progress(self) -> None:
        """Legacy: stop global progress bar."""
        if self._rich:
            self._delegate("stop_install_progress")

    def finish_install_progress(self) -> None:
        """Legacy: mark install progress complete."""
        if self._rich:
            self._delegate("finish_install_progress")
        self.show_install_complete()

    def update_install_progress(
        self,
        percent: int,
        step_num: int,
        total_steps: int,
        step_label: str,
        detail: str = "",
    ) -> None:
        """Legacy: update global install progress."""
        if self._rich:
            self._delegate("update_install_progress", percent, step_num, total_steps, step_label, detail)
        else:
            self.show_install_progress(step_label, percent, detail)


def lang_from_locale(locale_code: str) -> str:
    """Map a locale_code from LOCALE_CATALOG to its i18n_code.

    Args:
        locale_code: The locale code, e.g. ``"en_US"`` or ``"es_CL"``.

    Returns:
        The corresponding i18n code, e.g. ``"en_US"`` or ``"es_CL"``.
        Falls back to ``"en_US"`` if not found.
    """
    for _display, loc, i18n in LOCALE_CATALOG:
        if loc == locale_code:
            return i18n
    return "en_US"
