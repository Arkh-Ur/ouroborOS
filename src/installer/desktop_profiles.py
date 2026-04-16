"""desktop_profiles.py — ouroborOS desktop profile definitions.

Profiles are **package sets**, not curated configurations. ouroborOS does not
ship custom themes, keybindings, or desktop settings — each profile is a
starting point that the user configures however they want.

See docs/PHASE_2_PLAN.md for the rationale behind each package choice.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Profile package sets
# ---------------------------------------------------------------------------

PROFILE_PACKAGES: dict[str, list[str]] = {
    "minimal": [],
    "hyprland": [
        "hyprland",
        "xdg-desktop-portal-hyprland",
        "waybar",
        "foot",
        "hyprlauncher",         # Hypr ecosystem launcher (replaces wofi)
        "hyprpolkitagent",
        "hyprlock",             # lock screen — Hypr ecosystem (in extra)
        "hypridle",             # idle daemon — Hypr ecosystem (in extra)
        "hyprpaper",            # wallpaper setter — Hypr ecosystem (in extra)
        "hyprsunset",           # color temperature — Hypr ecosystem (in extra)
        "hyprland-qt-support",  # Qt6 Wayland integration
        "dunst",                # notifications (no Hypr-native notif daemon in extra)
        "grim",                 # screenshot backend
        "slurp",                # region selector for screenshots
        "thunar",               # file manager (lighter than dolphin, no KDE deps)
        "qt5-wayland",
        "qt6-wayland",
    ],
    "niri": [
        "niri",
        "xdg-desktop-portal-gnome",
        "foot",
        "fuzzel",
        "polkit-gnome",
        "waybar",          # status bar — essential for a tiling WM
        "mako",            # notifications
        "swaylock",        # lock screen
        "swaybg",          # wallpaper setter
        "swayidle",        # idle daemon (auto-lock)
        "qt5-wayland",
        "qt6-wayland",
    ],
    "gnome": [
        "gnome",
        "gnome-tweaks",
        "xdg-user-dirs",
    ],
    "kde": [
        # Plasma flavor is selected at install time (plasma / plasma-meta / plasma-desktop).
        # The flavor package is added dynamically by packages_for() based on kde_flavor.
        # Curated essential apps are always included on top.
        "dolphin",          # file manager
        "konsole",          # terminal
        "kate",             # text editor
        "gwenview",         # image viewer
        "ark",              # archive manager
        "ffmpegthumbs",     # video thumbnails in dolphin
    ],
    "cosmic": [
        # COSMIC is fully in [extra] as of 2026-04-15 — no AUR needed.
        "cosmic-session",           # session manager
        "cosmic-comp",              # Wayland compositor
        "cosmic-terminal",          # terminal emulator
        "cosmic-files",             # file manager
        "cosmic-launcher",          # app launcher
        "cosmic-settings",          # settings UI
        "cosmic-settings-daemon",   # settings daemon
        "cosmic-applets",           # system applets
        "cosmic-notifications",     # notification daemon
        "cosmic-bg",                # wallpaper/background
        "cosmic-idle",              # idle management
        "cosmic-panel",             # panel/taskbar
        "cosmic-osd",               # on-screen display
        "cosmic-app-library",       # app library/grid
        "xdg-desktop-portal-cosmic",
    ],
}

# AUR packages per profile — installed lazily via our-aur on first boot.
# These packages are NOT in official Arch repos and require makepkg.
# Build happens in ouroboros-firstboot to avoid stalling the installer.
# Empty list = no AUR packages for that profile.
PROFILE_AUR_PACKAGES: dict[str, list[str]] = {
    "minimal":  [],
    "hyprland": [
        "quickshell",    # Qt6/QML Wayland shell (not in official repos)
        # hyprlock, hypridle — moved to PROFILE_PACKAGES (now in [extra])
        # hyprshot — removed; grim+slurp already cover screenshots
    ],
    "niri":     [],      # niri is in [extra]; no AUR needed
    "gnome":    [],
    "kde":      [],
    "cosmic":   [],      # cosmic is fully in [extra]; no AUR needed
}

# ---------------------------------------------------------------------------
# KDE flavor selector
# ---------------------------------------------------------------------------
#
# Three plasma meta-packages are offered:
#   plasma         — full group (~1.5 GB, all Plasma components)
#   plasma-meta    — curated meta (~1 GB, recommended)
#   plasma-desktop — minimal (~400 MB, power users only)
#
# The flavor package is injected by packages_for() as the first entry.

_KDE_FLAVOR_PACKAGES: dict[str, str] = {
    "plasma":         "plasma",
    "plasma-meta":    "plasma-meta",
    "plasma-desktop": "plasma-desktop",
}

VALID_KDE_FLAVORS: frozenset[str] = frozenset(_KDE_FLAVOR_PACKAGES.keys())

# ---------------------------------------------------------------------------
# Display manager options (Wayland-native only)
# ---------------------------------------------------------------------------
#
# Five options are offered — all Wayland-native:
#   gdm    — GNOME Display Manager.  Full Wayland compositor.
#   sddm   — Simple Desktop Display Manager.  Wayland support via Qt.
#   plm    — Plasma Login Manager.  Fork of SDDM, native KDE integration.
#   greetd — Generic greeter daemon.  Used with cosmic-greeter for COSMIC.
#   none   — TTY login.  User launches their session manually.
#
# The "auto" value (default) resolves to the canonical DM for each profile,
# falling back to "none" for profiles that don't ship one.

VALID_DMS: frozenset[str] = frozenset({"gdm", "sddm", "plm", "greetd", "none"})

# Canonical DM for each profile (used when dm="auto")
_PROFILE_DEFAULT_DM: dict[str, str] = {
    "gnome":   "gdm",
    "kde":     "plm",
    "hyprland": "sddm",
    "niri":    "sddm",
    "cosmic":  "greetd",
}

# Pacman package for each DM (installed by pacstrap when needed)
_DM_PACKAGE: dict[str, str] = {
    "gdm":    "gdm",
    "sddm":   "sddm",
    "plm":    "plasma-login-manager",
    "greetd": "greetd",
}

# systemd service unit for each DM (used by configure.sh)
_DM_SERVICE: dict[str, str] = {
    "gdm":    "gdm",
    "sddm":   "sddm",
    "plm":    "plasmalogin",
    "greetd": "greetd",
}


def dm_package(dm: str) -> str:
    """Return the pacman package name for a display manager."""
    return _DM_PACKAGE[dm]


def dm_service(dm: str) -> str:
    """Return the systemd service name (without .service) for a display manager."""
    return _DM_SERVICE[dm]


def resolve_dm(profile: str, dm_choice: str = "auto") -> str:
    """Resolve the display manager for a profile + user choice.

    Args:
        profile: Desktop profile name.
        dm_choice: 'gdm', 'sddm', 'plasmalogin', 'greetd', 'none', or 'auto'.

    Returns:
        The resolved DM name.
    """
    if dm_choice == "auto":
        return _PROFILE_DEFAULT_DM.get(profile, "none")
    if dm_choice not in VALID_DMS:
        raise ValueError(
            f"Unknown display manager: {dm_choice!r}. "
            f"Valid options: {sorted(VALID_DMS)} + 'auto'"
        )
    return dm_choice


# ---------------------------------------------------------------------------
# Shell options
# ---------------------------------------------------------------------------
#
# Three shells are offered at install time:
#   bash — POSIX-compatible, default. Already part of 'base'.
#   zsh  — Bash-compatible with advanced completion and prompt customisation.
#   fish — Modern, user-friendly, non-POSIX (breaks legacy scripts).
#
# Bash is the default. Fish and Zsh are opt-in — users who want them know
# what they're choosing. Fish is intentionally last: its non-POSIX behaviour
# surprises users who expect standard shell semantics.

VALID_SHELLS: dict[str, str] = {
    "bash": "/bin/bash",
    "zsh":  "/bin/zsh",
    "fish": "/usr/bin/fish",
}

# Packages that need to be installed for each shell.
# bash is already included in the 'base' metapackage — no extra install needed.
SHELL_PACKAGES: dict[str, str] = {
    "zsh":  "zsh",
    "fish": "fish",
}


def shell_package(shell_name: str) -> str | None:
    """Return the pacman package for *shell_name*, or None if already in base."""
    return SHELL_PACKAGES.get(shell_name)


def shell_path(shell_name: str) -> str:
    """Return the absolute path for *shell_name*, or raise ValueError."""
    if shell_name not in VALID_SHELLS:
        raise ValueError(
            f"Unknown shell: {shell_name!r}. "
            f"Valid options: {sorted(VALID_SHELLS)}"
        )
    return VALID_SHELLS[shell_name]


# ---------------------------------------------------------------------------
# Legacy mapping (kept for backward compat — maps profile → default DM)
# ---------------------------------------------------------------------------

PROFILE_DM: dict[str, str] = dict(_PROFILE_DEFAULT_DM)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

VALID_PROFILES: frozenset[str] = frozenset(PROFILE_PACKAGES.keys())


def is_valid_profile(profile: str) -> bool:
    """Return True if *profile* is a known desktop profile name."""
    return profile in VALID_PROFILES


def packages_for(profile: str, kde_flavor: str = "plasma-meta") -> list[str]:
    """Return the package list for *profile*, or raise ValueError.

    For the 'kde' profile, the *kde_flavor* parameter controls which Plasma
    meta-package is prepended (plasma / plasma-meta / plasma-desktop).
    """
    if profile not in PROFILE_PACKAGES:
        raise ValueError(
            f"Unknown desktop profile: {profile!r}. "
            f"Valid profiles: {sorted(VALID_PROFILES)}"
        )
    pkgs = list(PROFILE_PACKAGES[profile])
    if profile == "kde":
        flavor_pkg = _KDE_FLAVOR_PACKAGES.get(kde_flavor, "plasma-meta")
        pkgs = [flavor_pkg] + pkgs
    return pkgs


def aur_packages_for(profile: str) -> list[str]:
    """Return the AUR package list for *profile* (may be empty)."""
    if profile not in PROFILE_AUR_PACKAGES:
        raise ValueError(
            f"Unknown desktop profile: {profile!r}. "
            f"Valid profiles: {sorted(VALID_PROFILES)}"
        )
    return list(PROFILE_AUR_PACKAGES[profile])


def display_manager_for(profile: str) -> str:
    """Return the display manager service name for *profile*, or ''."""
    return PROFILE_DM.get(profile, "")
