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

import logging
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

from installer.i18n import _, init_i18n

log = logging.getLogger("installer")

# Live install log tailed into the progress pane (same file the FSM writes to).
INSTALL_LOG_PATH = "/tmp/ouroborOS-install.log"
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# ouroborOS color palette for the animated progress bar (dark→bright green cycle).
PALETTE = ["#1a4d2e", "#2e7d32", "#43a047", "#66bb6a", "#a5d6a7"]

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
    ("Español (Chile)", "es_CL", "es_CL"),
    ("Español (Latinoamérica)", "es_MX", "es_MX"),
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
    hostname: str = "ouroboros"
    # Users (list of dicts matching show_users_creation() contract)
    users: list[dict] = field(default_factory=list)
    shell: str = "bash"
    # Desktop
    desktop_profile: str = "minimal"
    desktop_dm: str = "auto"
    gpu_driver: str = "auto"
    # Security
    secure_boot: bool = False
    tpm2_unlock: bool = False
    fido2_pam: bool = False
    root_password: str = ""
    set_root_password: bool = False
    # Disk
    disk_device: str = ""
    use_luks: bool = False
    luks_passphrase: str = ""
    partition_scheme: str = "auto"  # "auto" | "manual"
    manual_partitions: list[dict] = field(default_factory=list)
    # Network
    wifi_ssid: str = ""
    wifi_passphrase: str = ""
    enable_ssh: bool = False
    # Dotfiles pack
    dots_pack_id: str = ""           # empty string means "none selected"
    dots_pack_channel: str = "stable"
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
    from rich.text import Text as RichText
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.css.query import NoMatches
    from textual.screen import ModalScreen, Screen
    from textual.widgets import (
        Button,
        ContentSwitcher,
        Footer,
        Input,
        Label,
        ListItem,
        ListView,
        RadioButton,
        RichLog,
        Select,
        Static,
        TextArea,
    )

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


# ---------------------------------------------------------------------------
# Disk detection helper
# ---------------------------------------------------------------------------


def _live_medium_disk() -> str:
    """Return the parent disk backing the live ISO, e.g. '/dev/sda', or ''."""
    source = ""
    for mount in ("/run/archiso/bootmnt", "/"):
        result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", mount],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            source = result.stdout.strip()
            break
    if not source:
        return ""
    # Strip partition suffix to get the parent disk via PKNAME.
    pk = subprocess.run(
        ["lsblk", "-no", "PKNAME", source],
        capture_output=True,
        text=True,
        check=False,
    )
    name = pk.stdout.strip().splitlines()[0].strip() if pk.stdout.strip() else ""
    if name:
        return f"/dev/{name}"
    # Source may already be a whole disk (e.g. overlay on /dev/sda).
    base = source.split("/")[-1]
    return f"/dev/{base}" if base else ""


def _disk_size_bytes(size_str: str) -> int:
    """Parse lsblk size string (e.g. '20G', '940.1M', '4K') into bytes."""
    if not size_str or size_str == "?":
        return 0
    units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    size_str = size_str.strip()
    for suffix, factor in units.items():
        if size_str.upper().endswith(suffix):
            try:
                return int(float(size_str[:-1]) * factor)
            except ValueError:
                return 0
    try:
        return int(size_str)
    except ValueError:
        return 0


_MIN_DISK_BYTES = 1024**3  # 1 GiB — excludes floppy, ROM, tiny virtual devices


def _lsblk_disks() -> list[dict[str, str]]:
    """Return list of block devices suitable for installation (excludes live medium)."""
    import json

    result = subprocess.run(
        ["lsblk", "--json", "--output", "NAME,SIZE,MODEL,TYPE,HOTPLUG"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    live = _live_medium_disk()
    try:
        data = json.loads(result.stdout)
        disks = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") == "disk":
                name = f"/dev/{dev['name']}"
                if live and name == live:
                    continue
                size_str = dev.get("size", "?")
                if _disk_size_bytes(size_str) < _MIN_DISK_BYTES:
                    continue
                disks.append(
                    {
                        "name": name,
                        "size": size_str,
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
        """Animated ouroboros progress bar with a rolling green color cycle.

        Filled cells (▰) cycle through PALETTE colors; empty cells (▱) are dim.
        Call advance_cycle() on a timer to animate the palette shift.
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
            self._offset = 0

        def render(self) -> RichText:  # type: ignore[override]
            width = self.size.width or 40
            pct_part = f" {int(self._percent):>3}%"
            bar_width = max(4, width - len(pct_part))
            filled = int(self._percent / 100 * bar_width)
            empty = bar_width - filled

            text = RichText()
            for i in range(filled):
                color = PALETTE[(i + self._offset) % len(PALETTE)]
                text.append("▰", style=f"bold {color}")
            text.append("▱" * empty, style="dim #2e7d32")
            text.append(pct_part, style="bold #66bb6a")
            return text

        def update_percent(self, percent: float) -> None:
            """Update the displayed percentage and refresh."""
            self._percent = max(0.0, min(100.0, percent))
            self.refresh()

        def advance_cycle(self) -> None:
            """Shift the palette one step to animate the bar."""
            self._offset = (self._offset + 1) % len(PALETTE)
            self.refresh()

    class LogoWidget(Static):
        """Displays the ouroborOS braille logo in neon green on the screen background."""

        DEFAULT_CSS = """
        LogoWidget {
            background: transparent;
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
        ProgressPane #install-log {
            height: 1fr;
            border: round $primary;
            margin-top: 1;
        }
        ProgressPane #install-spinner {
            color: $accent;
        }
        """

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._log_offset = 0
            self._spin_idx = 0
            self._log_timer: Any = None
            self._spin_timer: Any = None
            self._cycle_timer: Any = None

        def compose(self) -> ComposeResult:
            yield Label(_("Installation Progress"), classes="section-title")
            yield Label("")
            yield GradientBar(label="", percent=0.0, id="bar-main")
            yield Label("", id="install-subtitle", classes="dim")
            yield Label("", id="install-step", classes="dim")
            yield Label("")
            yield Label("", id="progress-error", classes="error")
            yield Label(f"{SPINNER_FRAMES[0]} {_('working…')}", id="install-spinner")
            yield RichLog(id="install-log", highlight=False, markup=False, wrap=True, auto_scroll=True)

        def start_live(self) -> None:
            """Begin tailing the install log, animating the spinner and bar cycle."""
            self._log_offset = 0
            try:
                self.query_one("#install-log", RichLog).clear()
            except NoMatches:
                pass
            if self._log_timer is None:
                self._log_timer = self.set_interval(0.5, self._pump_log)
            if self._spin_timer is None:
                self._spin_timer = self.set_interval(0.12, self._spin)
            if self._cycle_timer is None:
                self._cycle_timer = self.set_interval(0.15, self._cycle_bar)

        def stop_live(self) -> None:
            """Stop all timers once the installation finished or errored."""
            for attr in ("_spin_timer", "_cycle_timer"):
                timer = getattr(self, attr, None)
                if timer is not None:
                    timer.stop()
                    setattr(self, attr, None)
            self._pump_log()
            try:
                self.query_one("#install-spinner", Label).update(f"✓ {_('done')}")
            except NoMatches:
                pass

        def _pump_log(self) -> None:
            """Read newly appended lines from the install log into the RichLog."""
            try:
                with open(INSTALL_LOG_PATH, encoding="utf-8", errors="replace") as fh:
                    fh.seek(self._log_offset)
                    new_data = fh.read()
                    self._log_offset = fh.tell()
            except OSError:
                return
            if not new_data:
                return
            try:
                rich_log = self.query_one("#install-log", RichLog)
            except NoMatches:
                return
            for line in new_data.splitlines():
                rich_log.write(line)

        def _spin(self) -> None:
            self._spin_idx = (self._spin_idx + 1) % len(SPINNER_FRAMES)
            try:
                self.query_one("#install-spinner", Label).update(
                    f"{SPINNER_FRAMES[self._spin_idx]} {_('working…')}"
                )
            except NoMatches:
                pass

        def _cycle_bar(self) -> None:
            try:
                self.query_one("#bar-main", GradientBar).advance_cycle()
            except NoMatches:
                pass

        def show_error(self, message: str) -> None:
            """Display an installation error inside the progress pane."""
            try:
                self.query_one("#progress-error", Label).update(message)
            except NoMatches:
                pass

        def update(self, global_pct: float, step_label: str = "", step_num: int = 0, total: int = 0) -> None:
            """Update the single bar + subtitle + step counter."""
            try:
                self.query_one("#bar-main", GradientBar).update_percent(global_pct)
            except NoMatches:
                pass
            if step_label:
                try:
                    self.query_one("#install-subtitle", Label).update(step_label)
                except NoMatches:
                    pass
            if step_num and total:
                try:
                    self.query_one("#install-step", Label).update(f"▸ {step_num}/{total}")
                except NoMatches:
                    pass

        def update_phase(self, phase: str, pct: float) -> None:
            """Legacy shim — forwards to the single-bar update."""
            self.update(pct, step_label=phase)

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
            yield Label(_("Installation Complete!"), classes="success")
            yield Label("")

            yield Label("", id="done-profile", classes="value")
            yield Label("", id="done-hostname", classes="value")
            yield Label("", id="done-locale", classes="value")
            yield Label("", id="done-disk", classes="value")
            yield Label("")
            yield Label(_("What would you like to do?"), classes="section-title")
            yield Label("")
            with Horizontal():
                yield Button(_("Reboot"), id="btn-reboot", classes="primary")
                yield Button(_("Shutdown"), id="btn-shutdown")
                yield Button(_("Exit to shell"), id="btn-exit")

        def on_mount(self) -> None:
            self.refresh_summary()

        def refresh_summary(self) -> None:
            """Re-read the live config from the buffer (it is filled after compose)."""
            profile = self._buffer.desktop_profile or "minimal"
            hostname = self._buffer.hostname or "(not set)"
            locale = self._buffer.locale
            disk = self._buffer.disk_device or "(not set)"
            self.query_one("#done-profile", Label).update(f"Desktop profile : {profile}")
            self.query_one("#done-hostname", Label).update(f"Hostname        : {hostname}")
            self.query_one("#done-locale", Label).update(f"Locale          : {locale}")
            self.query_one("#done-disk", Label).update(f"Disk            : {disk}")

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

    class NavSelect(Select):  # type: ignore[misc]
        """Select where arrows move between fields and enter/space opens.

        Textual's default binds up/down/enter/space all to "show_overlay".
        Form-style navigation wants arrows to move focus between fields and
        only enter/space to open the dropdown, so up/down are rebound to focus
        traversal. The open overlay keeps its own up/down for option picking.
        """

        BINDINGS = [
            Binding("enter,space", "show_overlay", "Open", show=False),
            Binding("up", "app.focus_previous", "Previous field", show=False),
            Binding("down", "app.focus_next", "Next field", show=False),
        ]

    class NavButton(Button):  # type: ignore[misc]
        """Button where arrows move focus; side-by-side Back/Apply use left/right.

        A plain Button has no arrow bindings, so two buttons in a Horizontal row
        cannot be traversed with the keyboard. Left/up move to the previous
        focusable, right/down to the next — so left/right hop between the
        adjacent Back and Apply buttons. enter/space still activate the button
        (inherited from Button).
        """

        BINDINGS = [
            Binding("left,up", "app.focus_previous", "Previous", show=False),
            Binding("right,down", "app.focus_next", "Next", show=False),
        ]

    class NavTextArea(TextArea):  # type: ignore[misc]
        """TextArea that releases focus when cursor_down is pressed on the last line.

        A plain TextArea swallows arrow keys for cursor movement, trapping
        keyboard focus. Tab already moves focus (TextArea.tab_behavior defaults
        to "focus"); this adds: pressing down on the final line hops to the next
        focusable field instead of doing nothing.
        """

        def action_cursor_down(self, select: bool = False) -> None:
            row, _col = self.cursor_location
            if row >= self.document.line_count - 1:
                self.app.action_focus_next()
                return
            super().action_cursor_down(select)

    class NavRadioButton(RadioButton):  # type: ignore[misc]
        """Standalone RadioButton (toggle) that arrows can navigate.

        A plain RadioButton has no arrow bindings, so up/down skip over it during
        field navigation. Up/down move focus between fields; enter/space still
        toggle the button (inherited from ToggleButton).
        """

        BINDINGS = [
            Binding("up", "app.focus_previous", "Previous field", show=False),
            Binding("down", "app.focus_next", "Next field", show=False),
        ]

    class LocalePane(Static):
        """Edit pane for locale/keymap/timezone configuration."""

        DEFAULT_CSS = "LocalePane { padding: 1 2; } LocalePane Select { margin-bottom: 1; }"

        # Locale options derived from the language catalog (value is the full
        # glibc locale string, e.g. "es_CL.UTF-8").
        _LOCALES = [(f"{display} ({code}.UTF-8)", f"{code}.UTF-8") for display, code, _ in LOCALE_CATALOG]
        _KEYMAPS = [
            ("US English (us)", "us"),
            ("UK English (uk)", "uk"),
            ("German (de)", "de"),
            ("Spanish (es)", "es"),
            ("Latin American (la-latin1)", "la-latin1"),
            ("French (fr)", "fr"),
            ("Italian (it)", "it"),
            ("Portuguese (pt-latin1)", "pt-latin1"),
            ("Brazilian (br-abnt2)", "br-abnt2"),
            ("Russian (ru)", "ru"),
            ("Dvorak (dvorak)", "dvorak"),
        ]
        _TIMEZONES = [
            ("UTC", "UTC"),
            ("America/New_York", "America/New_York"),
            ("America/Chicago", "America/Chicago"),
            ("America/Denver", "America/Denver"),
            ("America/Los_Angeles", "America/Los_Angeles"),
            ("America/Santiago", "America/Santiago"),
            ("America/Mexico_City", "America/Mexico_City"),
            ("America/Sao_Paulo", "America/Sao_Paulo"),
            ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires"),
            ("Europe/London", "Europe/London"),
            ("Europe/Madrid", "Europe/Madrid"),
            ("Europe/Paris", "Europe/Paris"),
            ("Europe/Berlin", "Europe/Berlin"),
            ("Europe/Rome", "Europe/Rome"),
            ("Europe/Moscow", "Europe/Moscow"),
            ("Asia/Tokyo", "Asia/Tokyo"),
            ("Asia/Shanghai", "Asia/Shanghai"),
            ("Australia/Sydney", "Australia/Sydney"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        @staticmethod
        def _initial(options: list[tuple[str, str]], current: str) -> str:
            """Return current if it is a known option value, else the first value."""
            values = [v for _, v in options]
            return current if current in values else values[0]

        def compose(self) -> ComposeResult:
            yield Label(_("Localization"), classes="section-title")
            yield Label("")
            yield Label(_("Locale:"))
            yield NavSelect(self._LOCALES, value=self._initial(self._LOCALES, self._buffer.locale),
                         allow_blank=False, id="select-locale")
            yield Label(_("Keymap:"))
            yield NavSelect(self._KEYMAPS, value=self._initial(self._KEYMAPS, self._buffer.keymap),
                         allow_blank=False, id="select-keymap")
            yield Label(_("Timezone:"))
            yield NavSelect(self._TIMEZONES, value=self._initial(self._TIMEZONES, self._buffer.timezone),
                         allow_blank=False, id="select-timezone")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-locale-apply", classes="primary")

        def _sync(self) -> None:
            """Write current widget values to the buffer (no focus change)."""
            try:
                locale_sel = self.query_one("#select-locale", Select)
                keymap_sel = self.query_one("#select-keymap", Select)
                tz_sel = self.query_one("#select-timezone", Select)
            except NoMatches:
                return
            if locale_sel.value is not Select.BLANK:
                self._buffer.locale = str(locale_sel.value)
            if keymap_sel.value is not Select.BLANK:
                self._buffer.keymap = str(keymap_sel.value)
            if tz_sel.value is not Select.BLANK:
                self._buffer.timezone = str(tz_sel.value)

        @on(Select.Changed, "#select-locale, #select-keymap, #select-timezone")
        def _on_select_changed(self, event: Select.Changed) -> None:
            self._sync()

        @on(Button.Pressed, "#btn-locale-apply")
        def _apply(self) -> None:
            self._sync()
            self.screen.action_focus_menu()

    class HostnamePane(Static):
        """Edit pane for hostname configuration."""

        DEFAULT_CSS = "HostnamePane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            yield Label(_("Hostname"), classes="section-title")
            yield Label("")
            yield Label(_("Enter a hostname for the installed system:"))
            yield Input(value=self._buffer.hostname or "ouroboros", id="input-hostname")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-hostname-apply", classes="primary")

        def _sync(self) -> None:
            """Write current widget value to the buffer (no focus change)."""
            try:
                val = self.query_one("#input-hostname", Input).value.strip()
                self._buffer.hostname = val or "ouroboros"
            except NoMatches:
                pass

        @on(Input.Changed, "#input-hostname")
        def _on_hostname_changed(self, event: Input.Changed) -> None:
            self._sync()

        @on(Button.Pressed, "#btn-hostname-apply")
        def _apply(self) -> None:
            self._sync()
            self.screen.action_focus_menu()

    class UsersPane(Static):
        """Edit pane for multi-user creation + optional root password."""

        DEFAULT_CSS = "UsersPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue
            self._suppress_root_toggle = False

        def compose(self) -> ComposeResult:
            yield Label(_("User & Authentication"), classes="section-title")
            yield Label("")
            yield Label(_("Added users:"))
            yield Vertical(id="users-list")
            yield Label("")
            yield Label(_("Username:"))
            yield Input(value="", id="input-username")
            yield Label(_("Full name (optional):"))
            yield Input(value="", id="input-realname")
            yield Label(_("Password:"))
            yield Input(value="", id="input-password", password=True)
            yield Label(_("Confirm password:"))
            yield Input(value="", id="input-password-confirm", password=True)
            with Horizontal(classes="button-row"):
                yield NavButton(_("Add user"), id="btn-user-add", classes="primary")
                yield NavButton(_("Remove last"), id="btn-user-remove")
            yield NavRadioButton(_("Set root password"), value=self._buffer.set_root_password, id="radio-root")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-users-apply", classes="primary")
            yield Label("", id="users-error", classes="error")

        def on_mount(self) -> None:
            self._refresh_list()

        def _refresh_list(self) -> None:
            container = self.query_one("#users-list", Vertical)
            container.remove_children()
            if not self._buffer.users:
                container.mount(Label(_("(none yet — add at least one)"), classes="dim"))
                return
            for i, u in enumerate(self._buffer.users):
                tag = _("primary") if i == 0 else _("user")
                container.mount(Label(f"• {u['username']} ({tag})", classes="value"))

        @staticmethod
        def _hash(password: str) -> str:
            import os as _os
            import subprocess as _sp
            salt = _os.urandom(16).hex()[:16]
            try:
                result = _sp.run(
                    ["openssl", "passwd", "-6", "-salt", salt, password],
                    capture_output=True, text=True, check=True,
                )
                return result.stdout.strip()
            except Exception:
                return ""

        @on(RadioButton.Changed, "#radio-root")
        def _toggle_root(self, event: RadioButton.Changed) -> None:
            if self._suppress_root_toggle:
                return
            if event.value:
                # Open a popup to capture the password instead of inline fields,
                # which were stranded below the fold of the scrollable pane.
                def _on_close(password: str | None) -> None:
                    if password is None:
                        # Cancelled — revert the radio without re-triggering this handler.
                        self._buffer.set_root_password = False
                        self._buffer.root_password = ""
                        self._suppress_root_toggle = True
                        try:
                            self.query_one("#radio-root", RadioButton).value = False
                        finally:
                            self._suppress_root_toggle = False
                        return
                    self._buffer.root_password = password
                    self._buffer.set_root_password = True

                self.app.push_screen(RootPasswordModal(self._buffer.root_password), _on_close)
            else:
                self._buffer.set_root_password = False
                self._buffer.root_password = ""

        @on(Button.Pressed, "#btn-user-add")
        def _add_user(self) -> None:
            error_label = self.query_one("#users-error", Label)
            username = self.query_one("#input-username", Input).value.strip()
            realname = self.query_one("#input-realname", Input).value.strip()
            password = self.query_one("#input-password", Input).value
            confirm = self.query_one("#input-password-confirm", Input).value
            if not username:
                error_label.update(_("Username cannot be empty."))
                return
            if any(u["username"] == username for u in self._buffer.users):
                error_label.update(_("That username is already added."))
                return
            if password != confirm:
                error_label.update(_("Passwords do not match."))
                return
            if len(password) < 4:
                error_label.update(_("Password must be at least 4 characters."))
                return
            # homed storage backend is derived from the disk config:
            # LUKS disk -> per-user LUKS home; otherwise a Btrfs subvolume.
            homed = "luks" if self._buffer.use_luks else "subvolume"
            is_primary = len(self._buffer.users) == 0
            groups = (
                ["wheel", "audio", "video", "input"] if is_primary else ["audio", "video", "input"]
            )
            self._buffer.users.append(
                {
                    "username": username,
                    "real_name": realname,
                    "password": password,
                    "password_hash": self._hash(password),
                    "homed_storage": homed,
                    "groups": groups,
                }
            )
            for fid in ("#input-username", "#input-realname", "#input-password", "#input-password-confirm"):
                self.query_one(fid, Input).value = ""
            error_label.update("")
            self._refresh_list()

        @on(Button.Pressed, "#btn-user-remove")
        def _remove_user(self) -> None:
            if self._buffer.users:
                self._buffer.users.pop()
                self._refresh_list()

        @on(Button.Pressed, "#btn-users-apply")
        def _apply(self) -> None:
            error_label = self.query_one("#users-error", Label)
            # Root password is captured via RootPasswordModal and already stored in
            # the buffer; only guard against a toggled-on radio with no password set.
            if self._buffer.set_root_password and len(self._buffer.root_password) < 4:
                error_label.update(_("Set a root password (at least 4 characters) or untoggle it."))
                return
            error_label.update("")
            self.screen.action_focus_menu()

    class EnvironmentPane(Static):
        """Unified pane for shell, desktop profile, display manager and GPU.

        Folds the old ShellPane/DesktopPane/GpuPane into one screen with four
        Selects so the whole environment is configured in a single place
        (bug #7). The 25 show_* contract is unchanged: show_shell_selection,
        show_desktop_profile, show_desktop_dm and show_gpu_driver each read
        their value from the buffer filled here.
        """

        DEFAULT_CSS = "EnvironmentPane { padding: 1 2; }"

        _SHELLS = [
            ("Bash — POSIX-compatible, universal default", "bash"),
            ("Zsh — advanced completion", "zsh"),
            ("Fish — modern and user-friendly", "fish"),
        ]
        _PROFILES = [
            ("minimal — Nothing extra (TTY only)", "minimal"),
            ("hyprland — Hyprland + Hypr ecosystem", "hyprland"),
            ("niri — Niri + foot + fuzzel", "niri"),
            ("gnome — GNOME desktop", "gnome"),
            ("kde — KDE Plasma", "kde"),
            ("cosmic — COSMIC Desktop", "cosmic"),
        ]
        _DMS = [
            ("auto — Recommended", "auto"),
            ("gdm — GDM", "gdm"),
            ("sddm — SDDM", "sddm"),
            ("plm — PLM", "plm"),
            ("greetd — greetd", "greetd"),
            ("none — TTY login", "none"),
        ]
        _GPUS = [
            ("auto — Auto-detect (default)", "auto"),
            ("mesa — Intel/AMD open source", "mesa"),
            ("amdgpu — AMD GPU explicit", "amdgpu"),
            ("nvidia — NVIDIA proprietary", "nvidia"),
            ("nvidia-open — NVIDIA open kernel module", "nvidia-open"),
            ("none — Skip, install manually", "none"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        @staticmethod
        def _initial(options: list[tuple[str, str]], current: str) -> str:
            values = [v for _, v in options]
            return current if current in values else values[0]

        def compose(self) -> ComposeResult:
            yield Label(_("Environment"), classes="section-title")
            yield Label("")
            yield Label(_("Login shell:"))
            yield NavSelect(self._SHELLS, value=self._initial(self._SHELLS, self._buffer.shell),
                         allow_blank=False, id="select-shell")
            yield Label(_("Desktop profile:"))
            yield NavSelect(self._PROFILES, value=self._initial(self._PROFILES, self._buffer.desktop_profile),
                         allow_blank=False, id="select-profile")
            yield Label(_("Display manager:"))
            yield NavSelect(self._DMS, value=self._initial(self._DMS, self._buffer.desktop_dm),
                         allow_blank=False, id="select-dm")
            yield Label(_("GPU driver:"))
            yield NavSelect(self._GPUS, value=self._initial(self._GPUS, self._buffer.gpu_driver),
                         allow_blank=False, id="select-gpu")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-environment-apply", classes="primary")

        def _sync(self) -> None:
            """Write current widget values to the buffer (no focus change).

            Called on every Select.Changed so the buffer always mirrors what
            the user sees — no silent revert to defaults if Apply is skipped.
            """
            try:
                shell_sel = self.query_one("#select-shell", Select)
                profile_sel = self.query_one("#select-profile", Select)
                dm_sel = self.query_one("#select-dm", Select)
                gpu_sel = self.query_one("#select-gpu", Select)
            except NoMatches:
                return
            if shell_sel.value is not Select.BLANK:
                self._buffer.shell = str(shell_sel.value)
            if profile_sel.value is not Select.BLANK:
                self._buffer.desktop_profile = str(profile_sel.value)
            if dm_sel.value is not Select.BLANK:
                self._buffer.desktop_dm = str(dm_sel.value)
            if gpu_sel.value is not Select.BLANK:
                self._buffer.gpu_driver = str(gpu_sel.value)

        @on(Select.Changed, "#select-shell, #select-profile, #select-dm, #select-gpu")
        def _on_select_changed(self, event: Select.Changed) -> None:
            self._sync()

        @on(Button.Pressed, "#btn-environment-apply")
        def _apply(self) -> None:
            self._sync()
            self.screen.action_focus_menu()

    class DiskPane(Static):
        """Edit pane for disk: target, partition scheme, and LUKS encryption.

        Folds the old EncryptionPane in here so disk layout and its encryption
        live together (bug #11). Two schemes (bug #10):
          - "auto"   -> partition_auto in disk.sh (GPT ESP + Btrfs subvolumes)
          - "manual" -> partition_manual in disk.sh, driven by a line-based spec
        """

        DEFAULT_CSS = "DiskPane { padding: 1 2; } DiskPane Select { margin-bottom: 1; }"

        _SCHEMES = [
            ("Automatic — GPT + Btrfs subvolumes (recommended)", "auto"),
            ("Manual — define your own partitions (advanced)", "manual"),
        ]
        # Placeholder shown in the manual editor; also the sensible default
        # ouroborOS layout so a user can tweak instead of starting blank.
        _MANUAL_TEMPLATE = "512MiB:esp:/boot:fat32\n100%:btrfs:/:btrfs"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        @staticmethod
        def _disk_options() -> list[tuple[str, str]]:
            opts = []
            for disk in _lsblk_disks():
                label = f"{disk['name']}  {disk['size']:>8}  {disk['model'][:30]}"
                opts.append((label, disk["name"]))
            return opts

        def compose(self) -> ComposeResult:
            yield Label(_("Disk Configuration"), classes="section-title")
            yield Label("")
            disk_opts = self._disk_options()
            yield Label(_("Target disk:"))
            if disk_opts:
                values = [v for _, v in disk_opts]
                initial = self._buffer.disk_device if self._buffer.disk_device in values else values[0]
                yield NavSelect(disk_opts, value=initial, allow_blank=False, id="select-disk")
            else:
                yield Label(_("No disks detected — enter a device path:"), classes="warning")
                yield Input(value=self._buffer.disk_device, placeholder="/dev/sda", id="input-disk-manual")
            yield Label(_("Partitioning:"))
            yield NavSelect([(_(lbl), val) for lbl, val in self._SCHEMES],
                         value=self._buffer.partition_scheme,
                         allow_blank=False, id="select-scheme")
            with Vertical(id="manual-fields"):
                yield Label(_("Manual layout — one partition per line: SIZE:TYPE:MOUNTPOINT:FS"),
                            classes="dim", id="manual-help")
                yield Label("TYPE: esp|btrfs|swap|linux · SIZE: 512MiB, 20GiB, 100%",
                            classes="dim", id="manual-help2")
                yield NavTextArea(
                    "\n".join(self._manual_lines()) if self._buffer.manual_partitions else self._MANUAL_TEMPLATE,
                    id="textarea-manual",
                )
            yield Label("")
            yield NavRadioButton(_("Encrypt disk with LUKS2"), value=self._buffer.use_luks, id="radio-luks")
            with Vertical(id="luks-fields"):
                yield Label(_("LUKS passphrase:"))
                yield Input(value="", password=True, id="input-luks-pass")
                yield Label(_("Confirm passphrase:"))
                yield Input(value="", password=True, id="input-luks-confirm")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-disk-apply", classes="primary")
            yield Label("", id="disk-error", classes="error")

        def on_mount(self) -> None:
            self.query_one("#luks-fields", Vertical).display = self._buffer.use_luks
            try:
                scheme = str(self.query_one("#select-scheme", Select).value)
            except NoMatches:
                scheme = self._buffer.partition_scheme
            self.query_one("#manual-fields", Vertical).display = scheme == "manual"

        @on(RadioButton.Changed, "#radio-luks")
        def _toggle_luks(self, event: RadioButton.Changed) -> None:
            self.query_one("#luks-fields", Vertical).display = event.value

        @on(Select.Changed, "#select-scheme")
        def _toggle_scheme(self, event: Select.Changed) -> None:
            self.query_one("#manual-fields", Vertical).display = str(event.value) == "manual"

        def _manual_lines(self) -> list[str]:
            lines = []
            for p in self._buffer.manual_partitions:
                lines.append(f"{p.get('size', '')}:{p.get('type', '')}:"
                             f"{p.get('mountpoint', '')}:{p.get('fs', '')}")
            return lines

        @staticmethod
        def _parse_manual(text: str) -> list[dict]:
            """Parse 'SIZE:TYPE:MOUNTPOINT:FS' lines into partition dicts."""
            parts: list[dict] = []
            for raw in (line.strip() for line in text.splitlines()):
                if not raw:
                    continue
                fields = raw.split(":")
                size = fields[0] if len(fields) > 0 else ""
                ptype = fields[1] if len(fields) > 1 else "linux"
                mountpoint = fields[2] if len(fields) > 2 else ""
                fs = fields[3] if len(fields) > 3 else ""
                parts.append({
                    "number": len(parts) + 1,
                    "size": size,
                    "type": ptype,
                    "mountpoint": mountpoint,
                    "fs": fs,
                })
            return parts

        def _selected_disk(self) -> str:
            try:
                return str(self.query_one("#select-disk", Select).value)
            except NoMatches:
                try:
                    return self.query_one("#input-disk-manual", Input).value.strip()
                except NoMatches:
                    return ""

        @on(Button.Pressed, "#btn-disk-apply")
        def _apply(self) -> None:
            try:
                error_label = self.query_one("#disk-error", Label)
                scheme = str(self.query_one("#select-scheme", Select).value)
                use_luks = self.query_one("#radio-luks", RadioButton).value
            except NoMatches:
                return

            disk = self._selected_disk()
            if not disk:
                error_label.update("Select or enter a target disk.")
                return

            manual_partitions: list[dict] = []
            if scheme == "manual":
                text = self.query_one("#textarea-manual", TextArea).text
                manual_partitions = self._parse_manual(text)
                mountpoints = {p["mountpoint"] for p in manual_partitions}
                types = {p["type"] for p in manual_partitions}
                if "/" not in mountpoints:
                    error_label.update("Manual layout needs a root partition (mountpoint '/').")
                    return
                if "esp" not in types:
                    error_label.update("Manual layout needs an ESP partition (type 'esp').")
                    return

            if use_luks:
                passphrase = self.query_one("#input-luks-pass", Input).value
                confirm = self.query_one("#input-luks-confirm", Input).value
                if passphrase != confirm:
                    error_label.update("Passphrases do not match.")
                    return
                if len(passphrase) < 4:
                    error_label.update("Passphrase must be at least 4 characters.")
                    return
                self._buffer.luks_passphrase = passphrase
            else:
                self._buffer.luks_passphrase = ""

            self._buffer.disk_device = disk
            self._buffer.use_luks = use_luks
            self._buffer.partition_scheme = scheme
            self._buffer.manual_partitions = manual_partitions
            error_label.update("")
            self.screen.action_focus_menu()

    class SecurityPane(Static):
        """Edit pane for Secure Boot, TPM2, and FIDO2 settings (toggles)."""

        DEFAULT_CSS = "SecurityPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            tpm_available = os.path.exists("/sys/class/tpm/tpm0")
            tpm_note = "" if tpm_available else " (no TPM2 detected)"

            yield Label(_("Security"), classes="section-title")
            yield Label("")
            yield NavRadioButton(_("Secure Boot (requires UEFI Setup Mode)"),
                              value=self._buffer.secure_boot, id="radio-secure-boot")
            yield NavRadioButton(_("TPM2 auto-unlock for LUKS") + tpm_note,
                              value=self._buffer.tpm2_unlock, id="radio-tpm2")
            yield NavRadioButton(_("FIDO2 PAM authentication"),
                              value=self._buffer.fido2_pam, id="radio-fido2")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-security-apply", classes="primary")

        @on(RadioButton.Changed, "#radio-secure-boot")
        def _on_secure_boot(self, event: RadioButton.Changed) -> None:
            self._buffer.secure_boot = event.value

        @on(RadioButton.Changed, "#radio-tpm2")
        def _on_tpm2(self, event: RadioButton.Changed) -> None:
            self._buffer.tpm2_unlock = event.value

        @on(RadioButton.Changed, "#radio-fido2")
        def _on_fido2(self, event: RadioButton.Changed) -> None:
            self._buffer.fido2_pam = event.value

        @on(Button.Pressed, "#btn-security-apply")
        def _apply(self) -> None:
            # Buffer-only: show_secure_boot/tpm2_unlock/fido2_pam read the buffer
            # (non-blocking). RadioButton.Changed already kept the buffer in sync;
            # this re-reads defensively in case an event was missed.
            try:
                self._buffer.secure_boot = self.query_one("#radio-secure-boot", RadioButton).value
                self._buffer.tpm2_unlock = self.query_one("#radio-tpm2", RadioButton).value
                self._buffer.fido2_pam = self.query_one("#radio-fido2", RadioButton).value
            except NoMatches:
                return
            self.screen.action_focus_menu()

    class NetworkPane(Static):
        """Edit pane for WiFi (scanned SSID + manual fallback), SSH, passphrase preview."""

        DEFAULT_CSS = "NetworkPane { padding: 1 2; }"

        _SCANNING_LABEL = "Scanning Wi-Fi…"
        _SCANNING_VALUE = "__scanning__"
        _MANUAL_LABEL = "✎ Enter SSID manually…"
        _MANUAL_VALUE = "__manual__"

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def compose(self) -> ComposeResult:
            initial = [(self._SCANNING_LABEL, self._SCANNING_VALUE), (self._MANUAL_LABEL, self._MANUAL_VALUE)]
            yield Label(_("Network"), classes="section-title")
            yield Label("")
            yield Label(_("WiFi SSID (leave on manual + blank to skip):"))
            yield NavSelect(initial, value=self._SCANNING_VALUE, allow_blank=False, id="select-wifi-ssid")
            yield Input(value=self._buffer.wifi_ssid, placeholder="SSID (used when 'Enter manually' is selected)",
                        id="input-wifi-manual")
            yield Label("")
            yield Label(_("WiFi passphrase:"))
            yield Input(value=self._buffer.wifi_passphrase, id="input-wifi-pass", password=True)
            yield NavRadioButton(_("Show passphrase"), value=False, id="radio-show-pass")
            yield Label("")
            yield NavRadioButton(_("Enable SSH"), value=self._buffer.enable_ssh, id="radio-ssh")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield NavButton(_("Back"), classes="btn-back")
                yield NavButton(_("Apply"), id="btn-network-apply", classes="primary")

        def on_mount(self) -> None:
            # Scan asynchronously via the Worker API so the event loop never
            # blocks on the iwctl subprocess (tui-textual architecture rule).
            self.run_worker(self._scan_wifi(), exclusive=True)

        async def _scan_wifi(self) -> None:
            import asyncio

            ssids = await asyncio.to_thread(self._scan_blocking)
            options = [(s, s) for s in ssids] + [(self._MANUAL_LABEL, self._MANUAL_VALUE)]
            try:
                select = self.query_one("#select-wifi-ssid", Select)
            except NoMatches:
                return
            select.set_options(options)
            select.value = ssids[0] if ssids else self._MANUAL_VALUE

        @staticmethod
        def _scan_blocking() -> list[str]:
            """Scan for Wi-Fi SSIDs via iwctl. Returns [] on any failure/timeout."""
            import re as _re

            def _run(args: list[str], timeout: float) -> str:
                try:
                    res = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
                    return res.stdout
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    return ""

            # Find a wireless station device (e.g. wlan0).
            station_out = _run(["iwctl", "station", "list"], 5)
            dev = ""
            for line in station_out.splitlines():
                clean = _re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                m = _re.match(r"(wl\w+|wlan\d+)\b", clean)
                if m:
                    dev = m.group(1)
                    break
            if not dev:
                return []

            _run(["iwctl", "station", dev, "scan"], 5)
            networks_out = _run(["iwctl", "station", dev, "get-networks"], 5)

            ssids: list[str] = []
            for line in networks_out.splitlines():
                clean = _re.sub(r"\x1b\[[0-9;]*m", "", line)
                clean = clean.replace(">", "").strip()
                if not clean or clean.lower().startswith(("available networks", "network name")):
                    continue
                if set(clean) <= {"-", " "}:
                    continue
                # Trailing columns are Security and Signal; SSID is the leading text.
                ssid = _re.split(r"\s{2,}", clean)[0].strip()
                if ssid and ssid not in ssids:
                    ssids.append(ssid)
            return ssids

        @on(RadioButton.Changed, "#radio-show-pass")
        def _toggle_pass(self, event: RadioButton.Changed) -> None:
            try:
                self.query_one("#input-wifi-pass", Input).password = not event.value
            except NoMatches:
                pass

        @on(RadioButton.Changed, "#radio-ssh")
        def _on_ssh(self, event: RadioButton.Changed) -> None:
            self._buffer.enable_ssh = event.value

        def _chosen_ssid(self) -> str:
            try:
                selected = str(self.query_one("#select-wifi-ssid", Select).value)
            except NoMatches:
                return ""
            if selected in (self._MANUAL_VALUE, self._SCANNING_VALUE, "Select.BLANK"):
                try:
                    return self.query_one("#input-wifi-manual", Input).value.strip()
                except NoMatches:
                    return ""
            return selected

        @on(Button.Pressed, "#btn-network-apply")
        def _apply(self) -> None:
            # Buffer-only: show_wifi_ssid/passphrase and show_ssh_enable read the
            # buffer (non-blocking). No queue.put.
            try:
                passphrase = self.query_one("#input-wifi-pass", Input).value
                ssh = self.query_one("#radio-ssh", RadioButton).value
            except NoMatches:
                return
            self._buffer.wifi_ssid = self._chosen_ssid()
            self._buffer.wifi_passphrase = passphrase
            self._buffer.enable_ssh = ssh
            self.screen.action_focus_menu()

    class PreviewPane(Static):
        """Default right-panel content: shows current buffer summary."""

        DEFAULT_CSS = "PreviewPane { padding: 1 2; }"

        def __init__(self, buffer: TUIBuffer, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer

        # Order mirrors the menu: Localization, Disk, Hostname, Users,
        # Environment, Network, Security.
        _ROWS = (
            "locale", "keymap", "timezone",
            "disk", "luks",
            "hostname",
            "users", "root",
            "shell", "desktop", "dm", "gpu",
            "ssid", "ssh",
            "secureboot", "tpm2", "fido2",
        )

        def compose(self) -> ComposeResult:
            yield Label(_("Installation Summary"), classes="section-title")
            yield Label("")
            for row in self._ROWS:
                yield Label("", id=f"sum-{row}", classes="dim")
            yield Label("")
            yield Label(_("Select a category from the left panel."), classes="dim")

        def on_mount(self) -> None:
            self.refresh_summary()

        def refresh_summary(self) -> None:
            """Repaint the summary from the current buffer (called after each Apply)."""
            b = self._buffer
            users_txt = ", ".join(u["username"] for u in b.users) if b.users else "(none)"
            dm_effective = "none (auto)" if b.desktop_profile == "minimal" else b.desktop_dm
            # (text, is_set) per row — is_set drives the green highlight.
            rows = {
                "locale": (f"Locale     : {b.locale}", True),
                "keymap": (f"Keymap     : {b.keymap}", True),
                "timezone": (f"Timezone   : {b.timezone}", True),
                "disk": (f"Disk       : {b.disk_device or '(not set)'}", bool(b.disk_device)),
                "luks": (f"LUKS       : {'Yes' if b.use_luks else 'No'}", b.use_luks),
                "hostname": (f"Hostname   : {b.hostname or '(not set)'}", bool(b.hostname)),
                "users": (f"Users      : {users_txt}", bool(b.users)),
                "root": (f"Root passwd: {'Yes' if b.set_root_password else 'locked'}", b.set_root_password),
                "shell": (f"Shell      : {b.shell}", True),
                "desktop": (f"Desktop    : {b.desktop_profile}", True),
                "dm": (f"DM         : {dm_effective}", dm_effective != "none (auto)"),
                "gpu": (f"GPU        : {b.gpu_driver}", True),
                "ssid": (f"WiFi SSID  : {b.wifi_ssid or '(none)'}", bool(b.wifi_ssid)),
                "ssh": (f"SSH        : {'Enabled' if b.enable_ssh else 'Disabled'}", b.enable_ssh),
                "secureboot": (f"Secure Boot: {'Yes' if b.secure_boot else 'No'}", b.secure_boot),
                "tpm2": (f"TPM2 unlock: {'Yes' if b.tpm2_unlock else 'No'}", b.tpm2_unlock),
                "fido2": (f"FIDO2 PAM  : {'Yes' if b.fido2_pam else 'No'}", b.fido2_pam),
            }
            for row, (text, is_set) in rows.items():
                try:
                    label = self.query_one(f"#sum-{row}", Label)
                except NoMatches:
                    continue
                label.update(text)
                label.set_class(is_set, "value")
                label.set_class(not is_set, "dim")

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
            # es_CL is hidden from the startup picker (it stays available in the
            # LocalePane). The original catalog index is preserved in the id so
            # _selected indexes LOCALE_CATALOG correctly.
            yield ListView(
                *[
                    ListItem(Label(display), id=f"lang-{i}")
                    for i, (display, locale_code, _ic) in enumerate(LOCALE_CATALOG)
                    if locale_code != "es_CL"
                ],
                id="language-list",
            )
            yield Footer()

        def on_mount(self) -> None:
            # The list must hold focus so Enter/arrows steer it from the start.
            self.query_one("#language-list", ListView).focus()

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
            # Seed the buffer so LocalePane, DonePane and the FSM reflect the
            # chosen language from the start (not the en_US.UTF-8 dataclass default).
            self.app._buffer.locale = f"{locale_code}.UTF-8"  # type: ignore[attr-defined]
            # switch_screen (not push) so the language screen is not left on the
            # stack — Escape on the menu should abort, not return here.
            self.app.switch_screen(MainMenuScreen(self.app._buffer, self.app._response_queue))  # type: ignore[attr-defined]

    class ConfirmEraseScreen(ModalScreen[bool]):  # type: ignore[misc]
        """Confirm full-disk erase before installation begins (bug #13)."""

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def __init__(self, device: str, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._device = device

        def compose(self) -> ComposeResult:
            with Vertical(id="confirm-dialog"):
                yield Label(_("Confirm installation"), classes="section-title")
                yield Label("")
                yield Label(_("The entire disk {device} will be ERASED.").format(device=self._device),
                            classes="warning")
                yield Label(_("This action cannot be undone."), classes="error")
                yield Label("")
                with Horizontal():
                    yield Button(_("Erase and install"), id="btn-confirm-erase", classes="danger")
                    yield Button(_("Cancel"), id="btn-cancel-erase")

        @on(Button.Pressed, "#btn-confirm-erase")
        def _confirm(self) -> None:
            self.dismiss(True)

        @on(Button.Pressed, "#btn-cancel-erase")
        def _cancel(self) -> None:
            self.dismiss(False)

        def action_cancel(self) -> None:
            self.dismiss(False)

    class RootPasswordModal(ModalScreen[str | None]):  # type: ignore[misc]
        """Popup to enter the root password (replaces the inline root-fields).

        Dismisses with the validated password string, or None if cancelled.
        """

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def __init__(self, initial: str = "", **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._initial = initial

        def compose(self) -> ComposeResult:
            with Vertical(id="root-dialog"):
                yield Label(_("Set root password"), classes="section-title")
                yield Label("")
                yield Label(_("Root password:"))
                yield Input(value=self._initial, id="modal-root-pass", password=True)
                yield Label(_("Confirm root password:"))
                yield Input(value=self._initial, id="modal-root-confirm", password=True)
                yield Label("", id="modal-root-error", classes="error")
                with Horizontal():
                    yield Button(_("Set"), id="btn-root-set", classes="primary")
                    yield Button(_("Cancel"), id="btn-root-cancel")

        def on_mount(self) -> None:
            self.query_one("#modal-root-pass", Input).focus()

        @on(Button.Pressed, "#btn-root-set")
        def _set(self) -> None:
            error_label = self.query_one("#modal-root-error", Label)
            root_pass = self.query_one("#modal-root-pass", Input).value
            root_confirm = self.query_one("#modal-root-confirm", Input).value
            if root_pass != root_confirm:
                error_label.update(_("Root passwords do not match."))
                return
            if len(root_pass) < 4:
                error_label.update(_("Root password must be at least 4 characters."))
                return
            self.dismiss(root_pass)

        @on(Button.Pressed, "#btn-root-cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

        def action_cancel(self) -> None:
            self.dismiss(None)

    class MainMenuScreen(Screen):  # type: ignore[misc]
        """Two-panel main menu screen."""

        # No global "q"→quit binding: a stray keystroke while a pane lacks focus
        # used to quit the installer outright. Escape now returns focus to the
        # left menu instead of aborting; aborting is the explicit "Abort" item.
        # Arrows move focus between fields within the active pane; the focused
        # ListView (left menu) and open Select overlays consume up/down first,
        # so menu navigation and option picking keep working. Enter/space open
        # a NavSelect; escape (or the Back button) returns to the menu.
        BINDINGS = [
            Binding("escape", "focus_menu", "Back to menu"),
            Binding("down", "focus_next", "Next field", show=False),
            Binding("up", "focus_previous", "Previous field", show=False),
        ]

        _MENU_ITEMS = [
            ("localization", "Localization"),
            ("disk", "Disk configuration"),
            ("hostname", "Hostname"),
            ("users", "Users & Authentication"),
            ("environment", "Environment"),
            ("network", "Network"),
            ("security", "Security"),
            ("separator", "───────────────────"),
            ("install", "Install"),
            ("abort", "Abort"),
        ]

        def __init__(self, buffer: TUIBuffer, response_queue: queue.Queue[Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = buffer
            self._q = response_queue

        def on_mount(self) -> None:
            # Cursor starts on the left category list so arrows/Enter steer it
            # immediately (bug #2) — mirrors LanguageScreen.on_mount.
            try:
                self.query_one("#main-menu", ListView).focus()
            except NoMatches:
                pass
            # Auto-assign the first detected disk so the Summary is populated and
            # an install can run straight from defaults (bug #13). The user can
            # still change it in "Disk configuration".
            if not self._buffer.disk_device:
                disks = _lsblk_disks()
                if disks:
                    self._buffer.disk_device = disks[0]["name"]
                    self._buffer.partition_scheme = "auto"
                    self._buffer.use_luks = False

        def compose(self) -> ComposeResult:
            yield LogoWidget()
            with Horizontal():
                with ScrollableContainer(id="left-panel"):
                    yield ListView(
                        *[
                            ListItem(
                                Label(label if key == "separator" else _(label)),
                                id=f"menu-{key}",
                            )
                            for key, label in self._MENU_ITEMS
                        ],
                        id="main-menu",
                    )
                with ScrollableContainer(id="right-panel"):
                    with ContentSwitcher(initial="pane-preview"):
                        yield PreviewPane(self._buffer, id="pane-preview")
                        yield LocalePane(self._buffer, self._q, id="pane-localization")
                        yield DiskPane(self._buffer, self._q, id="pane-disk")
                        yield HostnamePane(self._buffer, self._q, id="pane-hostname")
                        yield UsersPane(self._buffer, self._q, id="pane-users")
                        yield EnvironmentPane(self._buffer, self._q, id="pane-environment")
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
                return
            self._focus_pane(pane_id)

        def _focus_pane(self, pane_id: str) -> None:
            """Move keyboard focus to the first focusable widget of a pane."""
            try:
                pane = self.query_one(f"#{pane_id}")
            except NoMatches:
                return
            for widget in pane.query("Select, Input, RadioButton, TextArea, Button"):
                if widget.focusable:
                    self.set_focus(widget)
                    return

        def action_focus_menu(self) -> None:
            """Escape / Back: discard the open pane and return to the menu.

            Switches the right panel back to the read-only preview (so nothing
            half-edited is applied) and moves focus to the left category list.
            No queue.put and no buffer write — backing out never saves. The
            preview is repainted first so an Apply's new values show immediately.
            """
            self._refresh_preview()
            try:
                self.query_one(ContentSwitcher).current = "pane-preview"
            except NoMatches:
                pass
            try:
                self.set_focus(self.query_one("#main-menu", ListView))
            except NoMatches:
                pass

        def _refresh_preview(self) -> None:
            try:
                self.query_one("#pane-preview", PreviewPane).refresh_summary()
            except NoMatches:
                pass

        @on(Button.Pressed, ".btn-back")
        def _back_to_menu(self, event: Button.Pressed) -> None:
            """Any pane's Back button returns to the menu without applying."""
            event.stop()
            self.action_focus_menu()

        def _goto_pane(self, category: str, error_selector: str, message: str) -> None:
            """Switch to a pane and show a validation error in it."""
            pane_id = f"pane-{category}"
            try:
                self.query_one(ContentSwitcher).current = pane_id
            except NoMatches:
                return
            self._focus_pane(pane_id)
            try:
                self.query_one(error_selector, Label).update(message)
            except NoMatches:
                pass

        def _start_install(self) -> None:
            """Validate the buffer, then open the erase-confirmation modal.

            Validation happens BEFORE the modal so a missing field switches to the
            relevant pane with an error instead of starting a doomed install.
            """
            # Belt-and-suspenders: force widget→buffer sync for the pure-selection
            # panes in case the user changed a value without pressing Apply.
            for _pane_id, _pane_cls in [
                ("pane-localization", LocalePane),
                ("pane-hostname", HostnamePane),
                ("pane-environment", EnvironmentPane),
            ]:
                try:
                    self.query_one(f"#{_pane_id}", _pane_cls)._sync()
                except (NoMatches, AttributeError):
                    pass

            if not self._buffer.disk_device:
                self._goto_pane("disk", "#disk-error", _("Select a target disk before installing."))
                return
            if not self._buffer.users:
                self._goto_pane("users", "#users-error", _("Add at least one user before installing."))
                return
            if self._buffer.use_luks and not self._buffer.luks_passphrase:
                self._goto_pane(
                    "disk", "#disk-error",
                    _("LUKS is enabled — set a passphrase in Disk configuration."),
                )
                return

            device = self._buffer.disk_device

            def _on_confirm(confirmed: bool | None) -> None:
                if not confirmed:
                    return  # Cancelled — stay in the menu
                try:
                    switcher = self.query_one(ContentSwitcher)
                    switcher.current = "pane-progress"
                    # Hide the left menu and let progress fill the width while
                    # the installation runs.
                    self.query_one("#left-panel").display = False
                    self.query_one("#right-panel").styles.width = "100%"
                    # Begin tailing the install log + spinner in Textual's own
                    # thread (avoids call_from_thread for the live output).
                    self.query_one("#pane-progress", ProgressPane).start_live()
                except NoMatches:
                    pass
                # Unblocks show_locale_menu (the single install gate) in the FSM.
                self._q.put(True)

            self.app.push_screen(ConfirmEraseScreen(device), _on_confirm)

        def show_done(self) -> None:
            """Switch to the DonePane after installation completes."""
            try:
                self.query_one("#pane-progress", ProgressPane).stop_live()
            except NoMatches:
                pass
            try:
                self.query_one("#pane-done", DonePane).refresh_summary()
                switcher = self.query_one(ContentSwitcher)
                switcher.current = "pane-done"
            except NoMatches:
                pass

        def update_progress(
            self, global_pct: float, step_label: str = "", step_num: int = 0, total: int = 0
        ) -> None:
            """Update the single progress bar (called from FSM worker thread via call_from_thread)."""
            try:
                pane = self.query_one("#pane-progress", ProgressPane)
                pane.update(global_pct, step_label=step_label, step_num=step_num, total=total)
            except NoMatches:
                pass

        def show_error(self, message: str) -> None:
            """Surface an installation error on the progress pane."""
            try:
                self.query_one(ContentSwitcher).current = "pane-progress"
                pane = self.query_one("#pane-progress", ProgressPane)
                pane.stop_live()
                pane.show_error(message)
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
Screen { background: #000000; color: #d7ffe5; }
LogoWidget { background: transparent; color: #00FF66; height: auto; width: 100%; padding: 0; }
MainMenuScreen Horizontal { height: 1fr; }

/* Charm/Lip Gloss-look: rounded panels with a dim green accent border. */
#left-panel {
    width: 35%;
    height: 1fr;
    border: round #419E6E;
    background: #0a0a0a;
    padding: 0 1;
}
#right-panel {
    width: 65%;
    height: 1fr;
    border: round #419E6E;
    background: #0a0a0a;
    padding: 0 1;
}

/* Left menu: bright accent on the active row with a left marker bar; muted otherwise. */
ListView { background: transparent; }
ListView > ListItem { padding: 0 1; color: #8aa899; }
ListView > ListItem.--highlight {
    background: #00FF66;
    color: #000000;
    text-style: bold;
    border-left: thick #00FF66;
}

.section-title { color: #00FF66; text-style: bold; }
.value { color: #00FF66; }
.dim { color: #555555; }
.warning { color: #f4a261; }
.error { color: #d62828; }
.success { color: #00FF66; text-style: bold; }

/* Comboboxes collapse to a single row (button-height) so all fields stay
   visible without scrolling on small terminals; focus shown by background,
   not by a border that would add rows (bugs #3-#6). */
Select { width: 56; height: 1; margin-bottom: 1; }
Select > SelectCurrent { border: none; height: 1; padding: 0 1; }
Select:focus > SelectCurrent { border: none; background: #16432b; text-style: bold; }
Select SelectOverlay { max-height: 8; border: round #00FF66; }

Input { width: 56; height: 1; border: none; background: #11271b; padding: 0 1; }
Input:focus { background: #16432b; }
RadioButton { border: none; padding: 0 1; background: transparent; }
RadioButton:focus { text-style: bold; }

Button { border: round #419E6E; }
Button:focus { border: round #00FF66; }
Button.primary { background: #067B3B; color: #ffffff; }
Button.danger { background: #d62828; color: #ffffff; }
Button.btn-back { background: #1a1a1a; color: #00FF66; }
.button-row { height: auto; }
.button-row Button { margin-right: 2; }

GradientBar { height: 1; width: 100%; }
ProgressPane { padding: 1 2; height: 1fr; }

Footer { background: #0a0a0a; color: #555555; }
Footer > .footer--key { color: #00FF66; }

#language-screen { align: center middle; }
#language-screen ListView { width: 50; height: auto; max-height: 80%; border: round #419E6E; }
#language-list { width: 50; }

/* Modal confirmation dialog (erase-disk warning). */
ConfirmEraseScreen { align: center middle; background: $surface 60%; }
#confirm-dialog {
    width: 64;
    max-width: 80%;
    height: auto;
    max-height: 14;
    border: round #d62828;
    background: #0a0a0a;
    padding: 1 2;
}
#confirm-dialog Horizontal { height: auto; }
#confirm-dialog Button { margin: 1 1 0 0; }

/* Root password popup. */
RootPasswordModal { align: center middle; background: $surface 60%; }
#root-dialog {
    width: 64;
    max-width: 80%;
    height: auto;
    max-height: 18;
    border: round #5fafff;
    background: #0a0a0a;
    padding: 1 2;
}
#root-dialog Input { margin-bottom: 1; }
#root-dialog Horizontal { height: auto; }
#root-dialog Button { margin: 1 1 0 0; }
"""

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._buffer = TUIBuffer()
            self._response_queue: queue.Queue[Any] = queue.Queue()
            self._lang_queue: queue.Queue[Any] = queue.Queue()

        def on_mount(self) -> None:
            self.push_screen(LanguageScreen(self._response_queue, id="language-screen"))

        def update_progress(
            self, global_pct: float, step_label: str = "", step_num: int = 0, total: int = 0
        ) -> None:
            """Update progress bar from FSM worker thread."""
            try:
                screen = self.screen
                if hasattr(screen, "update_progress"):
                    screen.update_progress(  # type: ignore[attr-defined]
                        global_pct, step_label=step_label, step_num=step_num, total=total
                    )
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

        def show_error_screen(self, message: str) -> None:
            """Surface an installation error from the FSM worker thread."""
            try:
                screen = self.screen
                if hasattr(screen, "show_error"):
                    screen.show_error(message)  # type: ignore[attr-defined]
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

        While Textual owns the TTY, any StreamHandler writing to stderr/stdout
        on the root logger would paint log lines on top of the canvas. We detach
        those handlers for the lifetime of the app (keeping the FileHandler) and
        restore them on exit. Any crash is logged to the install log file —
        never to stderr — so the TUI never disappears without a trace.
        """
        import signal as _signal_mod

        _orig_signal = _signal_mod.signal

        def _thread_safe_signal(sig: Any, handler: Any) -> Any:
            try:
                return _orig_signal(sig, handler)
            except ValueError:
                return None  # not in main thread — skip

        _signal_mod.signal = _thread_safe_signal  # type: ignore[assignment]

        root_logger = logging.getLogger()
        detached = [
            h
            for h in list(root_logger.handlers)
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            and getattr(h, "stream", None) in (sys.stderr, sys.stdout)
        ]
        for handler in detached:
            root_logger.removeHandler(handler)

        try:
            self._app.run()  # type: ignore[union-attr]
        except Exception:
            logging.getLogger("installer").exception("Textual app crashed in _run_app")
        finally:
            _signal_mod.signal = _orig_signal  # type: ignore[assignment]
            for handler in detached:
                root_logger.addHandler(handler)

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
        """Return list of user configuration dicts (buffer-only, non-blocking).

        Park-at-gate: Install validates at least one user before unblocking the
        gate, so the buffer is always populated here. No _get() fallback — a
        blocking read would deadlock the FSM (the queue is empty after the gate).
        """
        if self._rich:
            return self._delegate("show_users_creation")
        return list(self._buffer.users)

    # ------------------------------------------------------------------
    # 4. show_shell_selection
    # ------------------------------------------------------------------

    def show_shell_selection(self) -> str:
        """Return shell name (bash/zsh/fish) from the buffer (non-blocking)."""
        if self._rich:
            return self._delegate("show_shell_selection")
        return self._buffer.shell or "bash"

    # ------------------------------------------------------------------
    # 5. show_desktop_profile
    # ------------------------------------------------------------------

    def show_desktop_profile(self) -> str:
        """Return desktop profile name from the buffer (non-blocking)."""
        if self._rich:
            return self._delegate("show_desktop_selection")
        return self._buffer.desktop_profile or "minimal"

    # ------------------------------------------------------------------
    # 6. show_desktop_dm
    # ------------------------------------------------------------------

    def show_desktop_dm(self, profile: str = "") -> str:
        """Return display manager name from the buffer (non-blocking)."""
        if self._rich:
            return self._delegate("show_dm_selection", profile=profile)
        return self._buffer.desktop_dm or "none"

    # ------------------------------------------------------------------
    # 7. show_gpu_driver
    # ------------------------------------------------------------------

    def show_gpu_driver(self) -> str:
        """Return GPU driver choice from the buffer (non-blocking)."""
        if self._rich:
            return self._delegate("show_gpu_selection")
        return self._buffer.gpu_driver or "auto"

    # ------------------------------------------------------------------
    # 8. show_secure_boot
    # ------------------------------------------------------------------

    def show_secure_boot(self) -> bool:
        """Return True if Secure Boot should be enabled (buffer, non-blocking)."""
        if self._rich:
            # Rich TUI shows an informational prompt (no bool return)
            self._delegate("show_secure_boot_prompt")
            return False
        return bool(self._buffer.secure_boot)

    # ------------------------------------------------------------------
    # 9. show_tpm2_unlock
    # ------------------------------------------------------------------

    def show_tpm2_unlock(self) -> bool:
        """Return True if TPM2 auto-unlock should be enabled (buffer, non-blocking)."""
        if self._rich:
            return self._delegate("show_tpm2_prompt")
        return bool(self._buffer.tpm2_unlock)

    # ------------------------------------------------------------------
    # 10. show_fido2_pam
    # ------------------------------------------------------------------

    def show_fido2_pam(self) -> bool:
        """Return True if FIDO2 PAM should be enabled (buffer, non-blocking)."""
        if self._rich:
            return False  # Rich TUI has no FIDO2 screen
        return bool(self._buffer.fido2_pam)

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

    def get_disk_scheme(self) -> tuple[str, list[dict]]:
        """Return (partition_scheme, manual_partitions) chosen in the DiskPane.

        Not part of the show_* contract — a buffer accessor the FSM uses to
        carry the manual layout into config.disk before running disk.sh.
        """
        if self._rich:
            return "auto", []
        return self._buffer.partition_scheme, list(self._buffer.manual_partitions)

    def get_root_password(self) -> str:
        """Return the root password from the buffer ('' = root account locked).

        Not part of the show_* contract — a buffer accessor the FSM uses to carry
        the optional root password into config.security before CONFIGURE.
        """
        if self._rich:
            return ""
        return self._buffer.root_password if self._buffer.set_root_password else ""

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
        return passphrase  # Buffer already confirmed in DiskPane

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
        return self._buffer.wifi_ssid

    # ------------------------------------------------------------------
    # 15. show_wifi_passphrase
    # ------------------------------------------------------------------

    def show_wifi_passphrase(self, ssid: str) -> str:
        """Return WiFi passphrase for the given SSID."""
        if self._rich:
            return ""  # Rich handles passphrase inside show_wifi_connect
        return self._buffer.wifi_passphrase

    # ------------------------------------------------------------------
    # 16. show_ssh_enable
    # ------------------------------------------------------------------

    def show_ssh_enable(self) -> bool:
        """Return True if SSH should be enabled (buffer, non-blocking)."""
        if self._rich:
            return False  # Rich TUI has no SSH screen
        return bool(self._buffer.enable_ssh)

    # ------------------------------------------------------------------
    # 17. show_partition_preview
    # ------------------------------------------------------------------

    def show_partition_preview(self, config: Any, use_luks: bool | None = None) -> bool:
        """Show partition layout. Returns True to confirm, False to abort.

        Accepts either a config object (``config.disk.device``/``use_luks``) or
        a (disk_path, use_luks) pair as the FSM passes them.
        """
        if self._rich:
            disk = getattr(getattr(config, "disk", None), "device", str(config))
            luks = use_luks if use_luks is not None else getattr(getattr(config, "disk", None), "use_luks", False)
            self._delegate("show_partition_preview", disk, luks)
            return True
        # Informational preview only. The erase gate is show_confirmation,
        # answered by the ConfirmEraseScreen modal (non-blocking here).
        return True

    # ------------------------------------------------------------------
    # 18. show_install_progress
    # ------------------------------------------------------------------

    def show_install_progress(self, phase: str, pct: int, msg: str) -> None:
        """Update install progress display."""
        if self._rich:
            self._delegate("show_progress", phase, msg, pct)
            return
        if self._app is not None:
            # The Textual app runs in a background daemon thread; if it has
            # already stopped (e.g. terminal disrupted), call_from_thread raises
            # RuntimeError("App is not running"). A progress repaint failure must
            # NEVER abort the install, so swallow and log instead of propagating.
            try:
                self._app.call_from_thread(self._app.update_progress, phase.lower(), float(pct))
            except Exception as exc:
                log.debug("Progress UI update skipped (app not running): %s", exc)

    # ------------------------------------------------------------------
    # 19. show_install_complete
    # ------------------------------------------------------------------

    def show_install_complete(self) -> None:
        """Show installation complete screen."""
        if self._rich:
            return
        if self._app is not None:
            try:
                self._app.call_from_thread(self._app.show_done_screen)
            except Exception as exc:
                log.debug("Done-screen update skipped (app not running): %s", exc)

    # ------------------------------------------------------------------
    # 20. show_install_error
    # ------------------------------------------------------------------

    def show_install_error(self, error: str) -> None:
        """Show installation error."""
        if self._rich:
            self._delegate("show_error", error, False)
            return
        if self._app is not None:
            try:
                self._app.call_from_thread(self._app.show_error_screen, error)
            except Exception as exc:
                log.debug("Error-screen update skipped (app not running): %s", exc)

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
        """Return KDE Plasma flavor (no pane answers this — safe default)."""
        if self._rich:
            return self._delegate("show_kde_flavor")
        return "plasma-meta"

    # ------------------------------------------------------------------
    # 24. show_dual_boot_enable
    # ------------------------------------------------------------------

    def show_dual_boot_enable(self) -> bool:
        """Return dual-boot choice (no pane answers this — safe default)."""
        if self._rich:
            return self._delegate("show_dual_boot_prompt", [])
        return False

    # ------------------------------------------------------------------
    # 25. show_sbctl_ms_keys
    # ------------------------------------------------------------------

    def show_sbctl_ms_keys(self) -> bool:
        """Return True if Microsoft OEM keys should be enrolled in sbctl."""
        if self._rich:
            return False  # Rich TUI has no sbctl_ms_keys screen
        val = self._get()
        return bool(val)

    def show_dots_pack_selection(self, profile: str) -> dict[str, str | None]:
        """Show dotfiles pack selection screen.

        Returns {"pack": id_or_none, "channel": "stable"|"git"}.
        If no internet, returns None pack regardless of buffer.
        """
        if self._rich:
            return self._delegate("show_dots_pack_selection", profile)
        # In pure Textual mode, check network before offering packs
        import subprocess  # noqa: PLC0415
        try:
            subprocess.run(
                ["getent", "hosts", "archlinux.org"],
                check=True, capture_output=True, timeout=3,
            )
            has_net = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            has_net = False
        if not has_net:
            return {"pack": None, "channel": "stable"}
        pack_id = self._buffer.dots_pack_id or None
        channel = self._buffer.dots_pack_channel or "stable"
        return {"pack": pack_id, "channel": channel}

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
        """Legacy: show error message.

        In Textual mode there is no interactive retry prompt during install, so
        we surface the error on the progress pane (instead of silently dropping
        it) and return False (no retry).
        """
        if self._rich:
            return self._delegate("show_error", message, recoverable)
        self.show_install_error(message)
        return False

    def show_confirmation(self, message: str) -> bool:
        """Legacy: show confirmation dialog.

        Park-at-gate: the disk-erase confirmation already happened in the
        ConfirmEraseScreen modal (which unblocked the gate via put(True)), so a
        _get() here would deadlock. Always confirm in Textual mode.
        """
        if self._rich:
            return self._delegate("show_confirmation", message)
        return True

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
        phase: str = "",
        sub_pct: int | None = None,
    ) -> None:
        """Legacy: update global install progress.

        ``phase`` is the stable FSM state name (e.g. ``"INSTALL"``) used to
        target the matching ProgressPane bar; ``step_label`` is a translated,
        human-readable label that must NOT be used as a widget id. ``sub_pct``
        is the per-phase percentage (0-100); when absent we fall back to the
        global ``percent``.
        """
        if self._rich:
            self._delegate("update_install_progress", percent, step_num, total_steps, step_label, detail)
        else:
            if self._app is not None:
                try:
                    self._app.call_from_thread(
                        self._app.update_progress,
                        float(percent),
                        step_label,
                        step_num,
                        total_steps,
                    )
                except Exception as exc:
                    log.debug("Progress UI update skipped (app not running): %s", exc)


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
